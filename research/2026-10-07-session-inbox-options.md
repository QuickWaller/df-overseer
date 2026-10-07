# Session and inbox options for the fort agents: what other frameworks and fields teach

Date: 2026-10-07. Read-only survey. No VM touched, nothing run. A live test of openclaw
multi-turn and reset is running separately and is not duplicated here.

Question (orchestrator, for a user discussion not yet decided): (1) every signal becomes
an item in a per-role inbox (one fact per item, priority, expiry, low priority items are
"warnings" that wait for the next wake); (2) one session per wake, the conductor pushes
items one at a time with per-turn and per-wake timeouts; (3) one long-lived session per
role, fed from a custom message queue, history wiped back to the system prompt between
wakes instead of compaction; (4) whether the Overseer gets items one per turn or grouped.
What related options exist and what do they teach?

Builds on `research/2026-10-07-persistent-sessions.md` (cost model, `agent exec` mints a new
session id per call, cross-run cache hypothesis), `research/2026-10-07-wake-audit.md` (the
note/warning mechanism, coalescing by fact) and `research/2026-10-07-cross-run-cache.md`.

Confidence key used below: F = fetched and read this session (primary docs or paper
abstract); R = recalled from prior knowledge, not re-fetched; P = from the earlier reports
in this repo.

## 1. Answer

1. **Idea (3), "long-lived session, wiped to the system prompt between wakes", is the same
   thing as "a fresh session each wake with a byte-stable prefix", plus a stable session
   key.** A wipe discards everything a long-lived session would carry, so what survives is
   the prefix and the identity. The value is not persistence; it is (a) cache-friendly
   prefix stability and (b) one serialised mailbox per role. Both can be had without a
   long-lived process. It is also what an actor restart does (original behaviour
   re-installed, mailbox kept, F for Akka) and what Temporal's continue-as-new does (R).
2. **The inbox (1) is the best-supported part and the one to build first.** Every mature
   queue and alerting system surveyed converges on five mechanisms: a coalescing key,
   per-item expiry, ack-on-completion (not on delivery), a strike counter ending in a
   dead-letter state, and aging so low priority work cannot starve. The wake audit already
   found the concrete failures these exist to prevent (five wakes for one fact; a deferred
   proposal re-waking forever).
3. **Items-per-turn (2) is a delivery detail, not a design.** It pays only if multi-turn in
   one session is cheap and robust, which the openclaw test decides. If not, the conductor
   chaining one-shot runs over the inbox gives the same per-item timeouts and strikes at the
   cost of one base prefix per run.
4. **For the ruling role, group by fact and show the whole docket first.** Evidence says
   side-by-side comparison gives cross-item consistency but list order and middle position
   hurt; this repo's own evidence (duplicate and repeat-deferred proposals) says singly
   judged items lose cross-item awareness. No study of proposal-ruling batching exists;
   this is inference (section 5).
5. **Recommendation: build the inbox as data and render it grouped into the existing
   one-shot briefing (design A). Add a session path (B, C, D) only if the openclaw test
   shows multi-turn works off the Gateway and a stable key plus reset fixes round-1 cache
   misses.**

## 2. Agent frameworks and platform guidance

### 2.1 Provider prompt caching (the constraint everything lives under)

- **Anthropic (F, platform docs).** Prefix order is tools, then system, then messages; a
  change at one level invalidates it and everything after. Default lifetime 5 minutes,
  refreshed free on each use; 1 hour at double write cost. Lookback is 20 blocks per
  breakpoint, so a growing conversation can walk past its last cache write and miss. The
  stated rule: breakpoint on "the last block whose prefix is identical across requests";
  the documented mistake is a per-request timestamp in the cached block. Lesson: the
  briefing (tick, wake reason) must stay last, which `conductor/briefing.py` already does.
- **Anthropic context editing (F).** Server-side clearing of old tool results and thinking
  blocks with `trigger` (default 100k tokens), `keep` (default last 3), `clear_at_least`.
  The docs say clearing "invalidates cached prompt prefixes" and to clear enough to make it
  worthwhile; clearing thinking blocks also invalidates from that point. Lesson: every
  mid-session history edit is a cache rewrite from the edit point on; only big, infrequent
  edits pay. A wipe once per wake is the extreme version (one rebuild, then stable). Not
  available for DeepSeek through openclaw; the mechanism is the lesson.
- **OpenAI (F).** Longest-prefix matching; stable instructions first, dynamic content
  after; `prompt_cache_key` groups related requests; retention up to 24 hours on earlier
  models, 30 minute minimum on the newest. Lesson: an explicit stable identity is how a
  provider that offers one keeps routing consistent. DeepSeek documents no such key.
- **DeepSeek (P, F earlier today).** Prefix matching, best effort, entries cleared "usually
  within a few hours to a few days", no fixed TTL; hits in our data at gaps up to 215
  minutes, none demonstrated after about 36 hours. Any design relying on a warm cache
  across a long idle gap bets on the weakest part of the provider.
- **OpenAI conversation state (F).** Server-held conversation objects or chaining by
  `previous_response_id`, where "all previous input tokens for responses in the chain are
  billed as input tokens", plus threshold compaction. Lesson: hosted threads charge for the
  whole thread every turn, same as ours.

### 2.2 Context management in agent frameworks

- **OpenHands condenser (F, project blog).** Summarises older interactions, keeps recent
  ones; per-turn cost settles at "less than half" of baseline, solve rate 54 percent vs 53.
  Key mechanism: condensation triggers only at thresholds, so cache rebuilds are amortised;
  baseline cost "scales quadratically", condensed "linearly".
- **JetBrains, "The Complexity Trap" (F, arXiv 2508.21433 abstract).** Observation masking
  (drop old tool outputs) halves cost and matches or slightly beats LLM summarisation on
  SWE-bench Verified across five model configurations; a hybrid is 7 to 11 percent cheaper
  again. Lesson: do not build an LLM summariser at the wake boundary; a wipe or
  deterministic mask is as good with no summary drift.
- **SWE-agent history processors (partly F).** The page fetched confirms only that
  `history_processors` is an ordered list in agent config with a `cache_control` processor
  taking `last_n_messages`. The other processors are R. Pattern: history shaping is an
  ordered pipeline and cache marking is one stage.
- **Letta / MemGPT (F partly).** Memory blocks are structured sections of the context
  window that "persist across all interactions", always visible, prepended in XML-like
  form, agent-editable and shareable across agents. The pages fetched say nothing on
  overflow or eviction; the tiered-memory premise is from the MemGPT paper (P). Lesson:
  Letta blocks are the "notebook" of persistent-sessions section 6. They sit at the top of
  the prompt, so an edit invalidates every later provider-side prefix (inference from
  prefix matching, not stated by Letta); our notebook goes after the stable prefix.
- **LangGraph (F).** A `thread_id` scopes checkpoints; checkpointers hold thread-scoped
  short-term state, stores hold cross-thread long-term memory; the docs note checkpoints
  accumulate in long conversations. Interrupts (pause and resume at a checkpoint) are R.
  Lesson: the clean split is thread = one wake's transcript, store = what survives, which
  is what the queue plus notebook already is.
- **AutoGen / AG2 (F, group chat page).** Agents publish and subscribe to a shared topic; a
  manager LLM picks the next speaker (never the same twice in a row); every agent extends
  its own history with every message. The docs say the example is "not meant to be used in
  real applications" and suggest simple rules over LLM calls for speaker selection.
  Lesson: shared-history message passing multiplies context per agent; our roles talking
  only through the queue is the cheaper opposite, and speaker choice stays deterministic
  (the conductor).
- **CrewAI (F, memory page).** A unified memory class with LLM-inferred scope and
  importance and recall blending similarity, recency and importance. The page does not
  state conversation state across kickoffs. Mild lesson: recency x importance is a
  reasonable ranking for which inbox items survive a cap (same as Generative Agents, R).
- **openclaw (F, docs on main via raw GitHub; not the installed image).**
  - `concepts/queue.md`: a per-session inbound queue with four modes. `followup` runs each
    queued message as its own turn after the current run; `collect` coalesces queued
    messages into one followup turn after a quiet window (debounce default 500 ms);
    `steer` injects into the active run; `interrupt` aborts it. Cap 20 per session; drop
    policy `summarize` (default), `old` or `new`. **This is the user's "custom message
    queue" and the "one at a time versus grouped" choice, already built as `followup`
    versus `collect`.** Caveat: documented for channel messages to a Gateway-owned session;
    whether it applies to `agent exec` or `--local` is not verified. The default
    `summarize` drop policy would create an unaudited, lossy second record of facts.
  - `concepts/session.md`: `/new` and `/reset` start a new session; optional `daily` and
    `idle` reset via `session.reset` and `resetByType`; default is no reset, compaction
    manages growth. The docs do **not** say whether the system prompt is byte-identical
    across a reset. That is the property idea (3) depends on and exactly what the live
    test should check.

## 3. Other fields

### 3.1 Actor model (Akka F; Erlang/OTP R)

- One message at a time per actor; the mailbox is the queue; a supervisor decides what
  failure means. Akka supervision (F): restart, stop, resume, and backoff (exponential
  delay before restart), with restart limits (for example 10 in 10 seconds). On restart the
  **message that caused the failure is removed from the mailbox**, other queued messages
  stay, and "the original Behavior ... is re-installed". Let-it-crash rationale: keep
  recovery out of business logic; crash and restart with validated state.
- Maps onto us: role = actor, inbox = mailbox, a timed-out or errored wake = a crash,
  conductor = supervisor, wipe to system prompt = restart with original behaviour. Akka's
  default drops the poison message; our wake audit shows the opposite default hurts (a
  timed-out Architect run is re-woken, re-reads everything, and can time out again, runs
  0010 and 0013). Borrow: a strike count per item, the failing item removed after N
  strikes and escalated, backoff between restarts.
- Pitfall: a restart limit with nothing downstream stalls silently. Ours has the
  human-alert path already used by the tripwire repeat brake.

### 3.2 Job queues (SQS F; others R)

- SQS (F): a visibility timeout hides a received message from other consumers; if not
  deleted before it expires it reappears; delivery is at-least-once, so duplicates inside
  the window are possible; a heartbeat can extend the timeout, with a 12 hour cap; repeated
  failures should go to a dead-letter queue. FIFO message groups serialise in-order work.
- Maps onto us: **an item is consumed when the role acknowledges it, not when delivered
  into a briefing.** Delivered but unacked items return with a strike. This is the
  difference between "the role saw it" and "the role dealt with it". The wake audit's
  row 8 (asker never woken for its answer) and row 9 (ruling arrives as "was ruled on" with
  no verdict) are both ack-semantics gaps.
- Pitfalls the field found: duplicate delivery (handlers must be idempotent; our propose
  and `queue.pass` already validate against queue state); a too-long timeout delays retry;
  an always-failing message circulates forever (DLQ plus a max-receive count, R for the
  exact attribute).
- Grouping and dedup: Prometheus Alertmanager's `group_by`, `group_wait`,
  `group_interval`, `repeat_interval` (R, not re-fetched) is the closest existing model:
  group by key, wait briefly to batch, do not re-notify inside an interval, re-notify an
  unresolved alert at a long interval. The wake audit's `coalesce.window_cycles` and
  doubling backoff are the same idea.
- Priority and starvation (R, general): strict priority queues starve the bottom; the
  standard cure is aging. "Warnings wait for the next wake" is a bottom class with no
  aging, so it needs the audit's `escalate_after_shows`: aging counted in shows, correct
  because ticks freeze under the operator hold.
- Work stealing (R): for interchangeable workers over a pool. Our roles are not
  interchangeable (different tool allowlists); the only transferable idea is that an item
  names the capability it needs, which is the audit's `acts_with`.

### 3.3 Workflow engines (Temporal, partly F)

- F: queries are read-only; **signals are asynchronous writes you cannot await a reply
  to**; updates are synchronous and validated before acceptance into history. Replay
  semantics: Temporal "doesn't restore memory from a snapshot", it re-runs the code and
  replays the event history. The pages fetched did not cover ordering, history limits or
  continue-as-new; those and the activity timeout family (schedule-to-start,
  start-to-close, heartbeat) are R.
- Maps onto us: a signal is an inbox item; an update is a validated write such as
  `queue.propose` (rejected at write time, as `dfqueue` already does). Per-turn timeout =
  start-to-close; per-wake timeout = run timeout. Continue-as-new (carry a small state into
  a fresh run to bound history) is the closest named pattern to "wipe history, keep the
  stable header, carry only a small curated state", and exists because unbounded history is
  the failure.
- Pitfall (R, medium): signal volume outrunning handling grows history without bound. Our
  cap-and-expire inbox is the equivalent bound.

### 3.4 Operating-system schedulers (R, textbook, not fetched)

- Time slices: a bounded slice then yield. Our per-turn and per-wake timeouts. Too short
  thrashes (each item pays orientation rounds; measured overseer base cost about $0.011 and
  5 to 14 rounds per wake, P); too long lets one item starve the rest. So slices should be
  coarse: a fact-group, not a signal.
- Priority inversion: a low priority item holds what a high priority one needs. Analogue:
  a deferred low priority proposal blocking a project step a high priority signal wants.
  Cure (inheritance): an item can name the item it blocks and ranks by the highest priority
  in its chain.
- Aging and starvation: see 3.2. Multilevel feedback demotes items that burn their slice;
  analogue: an item that exhausts its strikes goes to the human, not back to the top.

### 3.5 Triage and incident response (R, lowest confidence here)

- Emergency triage sorts by urgency and treats a cohort together when cases share a cause.
  Incident tooling (alert grouping, dedup keys, "page once, then attach later alerts to the
  incident") does the same. This is the wake audit's "one wake per (role, fact), later
  reasons arrive as lines", and independent support for the Overseer grouping by cause.
- Documented failure: alert storms from one cause paging repeatedly (our five-way drink
  pile-up) and alert fatigue. Reported cure: dedup at source, severity tiers where only the
  top tier interrupts, a periodic digest for the rest (our "warnings wait").

## 4. Pitfalls and the mechanism that answers each

| Pitfall (where found) | Our exposure | Mechanism worth borrowing |
|---|---|---|
| Duplicate delivery (SQS at-least-once) | Role crashes after acting, before ack | Idempotent handlers; item records the queue record id it produced |
| Poison message (SQS DLQ, Akka drops it) | An item that times the role out every time (Architect 607 s twice) | Strike count; N strikes then dead-letter plus human alert; no wake for a dead-lettered item |
| Starvation (OS aging, alert tiers) | Warnings never shown because wakes are rare | `escalate_after_shows`; a digest wake if warnings are older than a season |
| Cache invalidation (all three providers, OpenHands amortisation) | Anything placed before the briefing breaks the prefix | Items only in the briefing tail, stably sorted; no mid-wake history edits; one wipe per wake |
| Stale context (Laban, Context Rot, Letta blocks, Temporal history) | A role "remembers" drink was 0 | Items carry tick and expiry; briefing prints age; items name a fact key, tools re-read the fact |
| Unbounded growth (LangGraph checkpoints, Temporal history, openclaw cap 20) | Inbox accumulates through a long hold | Hard cap per role; overflow drops lowest priority first and logs it |
| Lossy summary (openclaw `summarize`, JetBrains result) | A summarised drop hides a real item | Drop to a deterministic count line, never an LLM summary |
| Woken for what it cannot act on | Architect woken on ore with no tool | `acts_with` check at policy load (wake audit section 4) |
| Hold semantics | Item arrives during operator hold | Decide once per item class (wake audit recommendation 8) |

## 5. Batching versus one at a time for a reviewer role

Evidence (F unless noted):

- **Position effects are robust.** Liu et al., "Lost in the Middle" (TACL): performance is
  highest when relevant information is at the start or end of the context and
  "significantly degrades" in the middle, including for long-context models.
- **Listwise judging is order-sensitive.** "Found in the Middle: Permutation
  Self-Consistency" (NAACL 2024): positional bias distorts listwise rankings; shuffling the
  list several times and aggregating gave 7 to 18 percent gains for GPT-3.5 and 8 to 16
  percent for a 70B model, at the cost of several calls.
- **LLM judges have position, verbosity and self-enhancement biases** (Zheng et al.,
  MT-Bench) but strong judges reach over 80 percent agreement with humans: correctable
  noise, not a veto.
- **Early-turn lock-in** (Laban et al., P): a 39 percent average multi-turn drop, models
  anchor on early assumptions. Applied to a sequence of items in one session, early rulings
  anchor later ones.
- Listwise is cheaper than pointwise (one call vs N) per a search summary of a survey page;
  medium confidence on the exact claim.

Not available: any study of LLM rulings over a small docket of heterogeneous proposals,
singly versus grouped. Everything below is inference from the above and this repo's data.

Inference for the Overseer (medium to low confidence):
- Singly in arrival order, the reviewer cannot see two proposals concern one fact. Live
  evidence: 6 of 13 Quartermaster work orders rejected as duplicate or infeasible, one
  proposal deferred three times (wake audit). Cross-item view is where quality comes from.
- A flat list of everything has the middle-position problem and order sensitivity. The
  docket is small (the ruling prompt already has an `OTHER OPEN ITEMS` block), which limits
  the effect but does not remove it.
- So: **a docket header (one line per open item with its fact key, highest priority first
  and last) then one fact-group per turn**, items within a group in a fixed order, plus a
  line saying which groups were already ruled this wake. Items sharing a fact key are one
  decision; unrelated groups are separate so a bad early ruling anchors the rest less.
- Randomising group order per wake (permutation consistency in spirit) is cheap but not
  recommended initially: stable order helps the cache and keeps audits reproducible.
- Advisors are proposers, not rankers; one fact-group at a time is natural for them and
  inbox coalescing already merges related items.

## 6. Candidate designs

### A. Inbox as data, one-shot run per wake, grouped rendering (no new execution path)

- Inbox table in the queue store: item id, role, fact key, priority class (mandatory, wake,
  note), text, created tick and cycle, expiry in cycles, shows, strikes, acked-by queue
  record id, `acts_with`. Coalesce on (role, fact key): a later item updates the earlier.
- Any wake-class item makes the role runnable; the briefing renders all of the role's open
  items (wake first, then notes), capped (wake audit: 6 lines of 200 characters) with a
  deterministic overflow count line.
- Ack on the role's recorded action or a `queue.pass` naming the fact; a run ending
  without ack gives the item a strike; three strikes dead-letter and alert the human.
- Overseer: docket header plus fact-groups in the one briefing, ruled in one run; on a
  timeout the unruled groups stay open.
- Pros: works with `agent exec` today, no cache dependence, auditable (inbox rows join to
  tool calls), fixes the audit's top findings. Cons: no per-item timeout (only the run's),
  one long run for a big docket, no cross-wake continuity (by design). Cost: a few hundred
  prompt tokens.

### B. Inbox plus one session per wake, items pushed per turn (user's idea 2)

- Conductor opens a session, sends the first fact-group, waits for the turn to finish
  (per-turn timeout), acks, sends the next, until drained or the per-wake budget is spent.
  The in-wake history is the cache-warm prefix.
- Pros: exact per-item timeouts and strikes; the conductor can reprioritise between groups
  (a tripwire mid-wake jumps the line); one bad group does not sink the rest.
- Cons: needs a multi-turn driver `agent exec` lacks (new session id per call, one turn, P);
  later turns replay reasoning on a growing history (cheap warm, three to five times a
  whole wake if cold at 400k, but here history is one wake's, so smaller); anchoring across
  groups (section 5); a Gateway or `--local` path.
- Versus "A chained by the conductor": per-item timeouts are equal; B saves roughly one
  base prefix per item (about $0.011 for the overseer even at a miss, P). Small.

### C. Long-lived session per role, custom queue, wipe between wakes (user's idea 3)

- Stable session key per role; the conductor is the only writer to the mailbox; between
  wakes it resets the session to the system prompt only.
- What it buys: (a) a stable key, which may remove the per-run id from the Runtime line (P
  section 3.4 hypothesis, unverified); (b) a serialised mailbox with actor semantics; (c) a
  wipe instead of compaction, no summary drift, consistent with JetBrains and OpenHands.
- What it does not buy: continuity (the wipe removes it) or any saving beyond (a).
- Risks: reset must leave the prefix byte-identical (unverified); a wipe racing an
  in-flight turn loses an item unless ack-on-completion is used; a charter or tool change
  cold-starts exactly as today; a long-lived process is one more thing to supervise, and
  the openclaw session store needs exclusive state-directory ownership (P).
- Verdict: only worth it as "fixed key plus reset between wakes" layered on A or B if the
  test shows it lifts round-1 cache hits. As an architecture it is B with a stable key.

### D. Hybrid: A as the data model, B for the Overseer only

- Everything uses the inbox of A. Advisors stay one-shot. The Overseer, with the largest
  docket and highest cost per run, runs one session per wake: docket header, one
  fact-group per turn, per-turn timeout, a hard stop leaving unruled groups open (a strike
  only if the turn itself failed).
- Pros: spends complexity where the evidence is (duplicate and repeat-deferred rulings).
  Cons: two execution paths; depends on the multi-turn test.

### Recommendation

1. **Build A now.** It depends on no openclaw result and its core (coalesce, ack, strikes,
   expiry, escalate-after-shows) is what every surveyed system agrees on. Fold in wake audit
   recommendations 1 to 4 and 9 as its first content.
2. **Treat B, C and D as delivery options on top of A, chosen by the test** (section 7).
3. If openclaw `collect` or `followup` is usable on these paths, use it rather than a
   custom queue, with drop policy `old` or `new` so no LLM summary of dropped facts exists.
4. When the cap bites, rank by priority class, then age (aging), then recency x importance;
   never an LLM summary.

## 7. What the openclaw test results would change

| Test outcome | Effect |
|---|---|
| Multi-turn works in one session through exec or a local path with a retained state dir | B and D become cheap; per-item timeouts native |
| Multi-turn needs the Gateway | Drop B and C; the conductor chains one-shots under A |
| Reset keeps system prompt and tool schemas byte-identical and round 1 then hits the cache | C's cache benefit is real; fixed key plus reset becomes default |
| Reset or a new session renders a changing value in the Runtime line | C's cache benefit is false; pin the field, the cross-run cache question stays open |
| A stable key alone changes round-1 hit rate | The saving is available to A with no session; do that first |
| `followup` or `collect` is honoured per session on these paths | Use them; set a non-summarising drop policy |
| A turn timeout leaves the session usable | Per-item timeouts are cheap; otherwise a timeout burns the session and counts as a wake-level failure |

## 8. Not verified

- All openclaw claims are from main-branch docs via raw GitHub, not the installed image;
  queue modes are documented for channel messages and Gateway sessions with no confirmation
  they apply to `agent exec` or `--local`.
- Letta overflow and eviction: the pages fetched did not cover it.
- SWE-agent processor details, LangGraph interrupts, Temporal continue-as-new and timeout
  types, SQS max-receive count, Alertmanager grouping parameters, actor and OS scheduler
  behaviour, triage practice, Generative Agents: recalled, not fetched this session.
- No source on LLM judgment quality for batched versus single proposal rulings; section 5
  is inference.
- DeepSeek v4 pro specifics (position bias, cache TTL): not measured; cache facts are from
  earlier reports.
- Whether the Runtime-line session key hypothesis (persistent-sessions 3.4) is true.
- Inbox volume: the wake audit's data is 21 runs on a mostly paused fort, so cap values
  are guesses.

## Sources

Fetched this session: Anthropic platform docs (prompt caching, context editing); OpenAI
developer docs (prompt caching, conversation state); AWS SQS developer guide (visibility
timeout); Akka typed fault tolerance; Temporal docs (message passing, workflows); LangChain
LangGraph persistence; Letta docs (memory blocks); AutoGen group chat pattern; CrewAI
memory; OpenHands condenser blog; arXiv 2508.21433, 2310.07712, 2306.05685, 2307.03172;
openclaw `docs/concepts/queue.md` and `docs/concepts/session.md` (main). Repo: the three
research files named at the top, `conductor/briefing.py`, `conductor/triage.py`.
