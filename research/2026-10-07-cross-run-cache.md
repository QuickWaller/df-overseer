# Cross-run prompt-cache hits for the fort agents (DeepSeek v4 pro via openclaw)

Date: 2026-10-07. Read-only investigation; nothing on any VM was written or run.

## Answer

**Yes, there are cross-run hits, but they are partial and erratic, not reliable.**
Per-turn usage is not stored anywhere, so "cacheRead on turn 1" cannot be read
directly. It can be bounded from per-run totals and rounds. Six of 17 runs
**provably** had a turn-1 hit (no assumption beyond "the prompt never shrinks
within a run"), at gaps of 0 to 215 minutes since that role's previous run. The
rest are unproven (neither a hit nor a miss is demonstrated). The runs after a
gap of about 36 hours show no sign of a hit (confidence medium).

The earliest point that varies between runs for one role is **not early**: the
briefing (game tick, wake reason, vitals) is the final positional argument, so
it is the last thing in the prompt. Per the runner's own code comment,
openclaw's system prompt ends in a `## Runtime` line (`host=`), which the fixed
`--hostname <role>` made stable. What I could not verify is whether anything
else in openclaw's system prompt (a date or time, a file listing, ordering)
varies earlier. See Not verified.

So the structure is already close to optimal. The remaining waste is about
**$0.17 of $0.81 (at most about 21%)** across the 17 measured runs, an upper
bound that assumes the whole turn-1 prompt was cacheable. Realistically less,
since the briefing part of turn 1 is new every time. Output tokens are 52% of
cost and uncached input 45%, so the bigger levers are fewer rounds and less
reasoning, not cache layout.

## Data sources and what was missing

- Runs DB (`runs` table, 21 rows, 2026-10-05 and 06): columns are id, role,
  wake, timestamps, status, duration, cost_usd, records_json, thinking. **No
  usage, cache or turns columns.** The schema described in the task does not
  match.
- Usage lives in the conductor's archived `run-<role>.json` envelopes under the
  conductor runtime directory on the agent VM (`usage`, `assistant_turns`,
  `cost_usd`). Only runs from 2026-10-05 08:29 onward carry usage (stage 0
  added it): 17 runs. Earlier envelopes have no usage. I joined them to the
  runs DB by role plus wall-clock duration (within 1.5 s).
- No per-turn usage anywhere: the openclaw state databases hold no session
  transcripts (the agent databases hold only FTS shells, the state database has
  no transcript table), and the conductor journal holds no `usage=` lines (0
  hits in 14 days). The stage 0 README already said "cross-run cache:
  inconclusive, per-round usage needed"
  (`evals/live/2026-10-05-execution-stage-0/README.md`).

## Method (inference from totals)

Let P_t be the prompt size of turn t, T the turns, H the turn-1 cross-run hit.
Assume turn t>1 hits the whole previous prompt (DeepSeek caches at request
boundaries) and the prompt only grows. Then:

- input (uncached) = P_T - H; cacheRead = H + sum(P_1..P_{T-1});
  input + cacheRead = sum(P_t).
- Since P_T >= mean(P) = (input + cacheRead)/T, **H >= (input + cacheRead)/T - input**
  (call it H_lb0). If positive, a turn-1 hit is proven.
- A tighter bound adds growth: each round adds at least its own output
  (output/T) to the next prompt, so H_lb1 = mean + (output/T)(T-1)/2 - input.
  This assumes openclaw replays reasoning and tool-call text in later turns; if
  it does not, H_lb1 overstates. Medium confidence, shown as a second column.

Confidence: H_lb0 positive is high confidence unless openclaw prunes or
compacts context mid-run (not checked; that would break monotonicity). H_lb0
negative proves nothing.

## Per-run table

Gap = minutes since the end of that role's previous run in the runs DB. T =
assistant turns. Sizes in tokens.

| Run | Role | Gap min | T | Input | CacheRead | H_lb0 | H_lb1 | Hit? |
|---|---|---|---|---|---|---|---|---|
| 0005 | quartermaster | 163 | 9 | 31,219 | 292,096 | 4,705 | 15,062 | proven |
| 0006 | quartermaster | 0 | 9 | 28,426 | 285,440 | 6,448 | 18,983 | proven |
| 0007 | overseer | 163 | 13 | 63,332 | 875,008 | 8,848 | 21,011 | proven |
| 0008 | architect | 215 | 7 | 47,769 | 309,760 | 3,307 | 15,439 | proven |
| 0009 | quartermaster | 44 | 7 | 33,434 | 140,416 | 0 | 0 | unproven |
| 0010 | architect | 3 | 6 | 46,731 | 163,712 | 0 | 5,382 | unproven (timeout run) |
| 0011 | quartermaster | 10 | 7 | 53,595 | 198,784 | 0 | 0 | unproven |
| 0012 | overseer | 55 | 5 | 71,912 | 254,720 | 0 | 0 | none likely (input about equals mean) |
| 0013 | architect | 29 | 10 | 50,704 | 415,488 | 0 | 16,721 | unproven (timeout run) |
| 0014 | quartermaster | 36 | 7 | 24,994 | 213,120 | 9,022 | 18,140 | proven |
| 0015 | consultant | none | 11 | 43,522 | 408,704 | 0 | 8,891 | unproven |
| 0016 | overseer | 42 | 5 | 31,878 | 328,064 | 40,110 | 54,573 | proven, near-full prefix |
| 0017 | architect | 2,154 | 4 | 36,781 | 105,728 | 0 | 1,140 | likely none |
| 0018 | quartermaster | 2,150 | 8 | 57,616 | 337,664 | 0 | 6,312 | unproven |
| 0019 | overseer | 2,143 | 9 | 86,123 | 676,864 | 0 | 8,435 | unproven |
| 0020 | quartermaster | 9 | 14 | 74,483 | 863,104 | 0 | 28,057 | unproven (H_lb1 says hit) |
| 0021 | overseer | 16 | 7 | 57,091 | 311,424 | 0 | 5,046 | unproven |

Reading it:

- Run 0016 is the clean case: five rounds, 32k uncached input against a mean
  prompt of 72k, so nearly the whole stable prefix (40k or more) was read from
  cache at turn 1. Run 0012, the same role earlier the same morning with about
  the same shape (five rounds, 72k input), shows no hit. Gap length does not
  explain it (55 min versus 42 min). One possible cause: before 0016, other
  roles (consultant, quartermaster) ran minutes earlier and may have stored a
  shared prefix. I could not confirm that.
- Hits were proven at gaps up to 215 minutes (0008). DeepSeek says only that
  unused cache is cleared "usually within a few hours to a few days", which is
  consistent; no fixed TTL exists. After the roughly 36 hour gap (0017 to 0019)
  no hit is demonstrated, and 0017's total output (6k tokens in 4 rounds) is
  too small to hide a large hit. Medium confidence.
- Estimated turn-1 prompt P1 (mean minus growth; rough, assumes linear
  growth): overseer about 59k, architect about 29k, quartermaster about 27k,
  consultant about 30k. The overseer's prefix is twice the others, so a miss
  costs it twice as much.

## What DeepSeek documents (primary source read 2026-10-07)

From the DeepSeek API guide on context caching (api-docs.deepseek.com, KV cache
page):

- Enabled by default; overlapping prefixes with previous requests are fetched
  from cache. A request hits only if it "fully matches a cache prefix unit".
- Cache entries are persisted at request boundaries (end of user input and of
  model output), at common prefixes detected across requests, and at fixed
  token intervals for long inputs.
- Hits are reported as `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`.
- "Best-effort": no guarantee of a 100% hit rate. Unused cache is cleared
  "usually within a few hours to a few days". **No fixed TTL is documented.**
- The page fetched did not state a minimum length or prefix-unit size; not
  confirmed.

Consequence: any change before the briefing (a charter edit on deploy, a
tool-schema change, a reordered tool list) cuts the matched prefix at that
point. Deploys on 10-05 and 10-06 changed charters and allowlists, so some
misses above may be deploy invalidations rather than expiry.

## Cost model (derived, high confidence on the fit)

A least-squares fit of the 17 runs' `cost_usd` against (input, cacheRead,
output) is exact (residual about 1e-33): **$0.435 per M uncached input,
$0.0036 per M cache read, $0.87 per M output.** A cache read is 120 times
cheaper than a miss. These are not DeepSeek's published v4-pro list rates (the
pricing page, fetched today: off-peak $0.66 miss, $0.022 hit, $1.98 output; peak
double), so openclaw's configured prices differ from the list, or a promotion
applies. I did not find out which.

Cost split over the 17 runs ($0.81 total): output 52%, uncached input 45%,
cache reads 3%.

## Cost saving if the prefix were fully cached at turn 1

Upper bound = (estimated P1 minus proven hit H_lb1) times $0.4314 per M (miss
minus hit rate). Per run it ranged $0.001 to $0.029. Per-role means: overseer
$0.018 per run (about 35% of its mean $0.050 cost), architect $0.008,
consultant $0.009, quartermaster $0.006. Total across the 17 runs about $0.17 of
$0.81. Cautions: P1 includes the new briefing (never cacheable), and H_lb1
assumes reasoning replay, so this is a ceiling, probably 2 to 3 times too high
for the roles with small prefixes.

## What would actually move the number

1. Do not reorder anything; the briefing is already last. Keep charters, tool
   lists and the runtime line byte-stable between deploys (batch deploys, avoid
   cosmetic charter edits).
2. Run wakes close together; hits were proven at 0 to 215 minutes but not
   demonstrated across a day. The overseer prefix is the largest (about 59k),
   so it gains most from running soon after another role (run 0016).
3. Capture per-round usage (`prompt_cache_hit_tokens`) in the archive. That
   turns this inference into a measurement. Needs openclaw support or a proxy
   log; not investigated.

## Not verified

- Turn-1 `cacheRead` directly (per-turn data not stored). All hit sizes are
  inferred bounds.
- Whether openclaw prunes or compacts context mid-run, or replays reasoning
  (affects H_lb0 validity and H_lb1).
- The content and order of openclaw's system prompt (no access to the image:
  docker is not permitted for the user on the agent VM, and no repo copy of a
  rendered prompt exists). Whether a date, time, session id or file listing sits
  before the charter is unknown; the `## Runtime` line is known only from the
  runner's code comment.
- Whether the hit in 0016 came from the same role's earlier run or from another
  role's shared prefix.
- Earlier runs (about 22 older envelopes) before 2026-10-05 08:29 (no usage archived).
- Peak versus off-peak pricing effects; the origin of openclaw's price table.
