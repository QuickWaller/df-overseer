# Handoff: `dfseries` understands resetting timers

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.**

Read `CLAUDE.md`, then `docs/TIMESERIES.md` in full, **especially the section
"Timers reset: a rate across a reset is meaningless"**, then `dfseries/`
(all of it, it is small), then this.

## The bug

`thirst_timer`, `hunger_timer` and `sleepiness_timer` are **counters that
reset**, not levels. `dfseries` treats every metric as a level, so on the first
real run `unit:192`, who drank mid-run (33,722 to 1,085), got a rate of
**-2.133056 per tick over 10 samples**. It looks authoritative and means
nothing. That is the failure class this project keeps catching: a confident
number standing in for no answer.

## The key fact, and its limit

A timer that rises exactly 1 per tick **is** "ticks since the last reset". So
between consecutive samples at ticks `t0` and `t1` with values `v0` and `v1`:

- `v1 == v0 + (t1 - t0)`: no reset.
- `v1 < v0 + (t1 - t0)`: **at least one reset, and the last one happened at
  exactly `t1 - v1`**. The sample itself dates the event to the tick. (A value
  that rose, but by less than the tick gap, is still a reset: 500 then 1,100
  across a 1,200-tick gap means a reset at `t1 - 1100`.)
- `v1 > v0 + (t1 - t0)`: impossible for a 1-per-tick counter. Report it as an
  anomaly. Never absorb it.

**That exactness depends on the rate being exactly 1 per tick, and that is
proven only for thirst**: 206 of 207 real citizen-intervals rose by exactly the
tick gap, and the one exception was a real drink (`handoffs/2026-09-19-sampler.md`).
**Hunger is unproven. Sleepiness is very likely not 1 per tick at all**, since
in DF it drains while a dwarf sleeps rather than snapping to zero. So:

- **Measure each timer's between-reset rate from the real data** (below)
  before assigning it exact-timing treatment.
- A metric whose rate is not established gets **interval-bounded** events
  (a reset somewhere in `(t0, t1]`), stated as such, never an exact tick.

## Deliverable

1. **A metric-kind registry**: `level` versus `resetting_counter`, with, for
   each resetting counter, its **established rate and the evidence for it**,
   or "not established". Unknown metrics default to `level`, and **every trend
   output states which kind it assumed**.
2. **`trend.resets(...)`**: the reset events for a subject's metric over a
   window, each exact-tick or interval-bounded, and anomalies reported
   separately.
3. **`trend.rate(...)` on a resetting counter must refuse to straddle a
   reset.** Return `unavailable` with a reason naming the reset and pointing
   at `resets()`, or return the between-reset slope with that stated. Never
   the endpoint slope.
4. **Fort-level events per dwarf-day**: aggregate resets across every
   `unit:*` subject for a metric over a window, divided by citizen-days
   observed. For thirst that is **drinking events per dwarf-day**, the
   demand-side figure the production model has wanted since the start and has
   never had. Name it drinking **events**, not drink consumption: a thirst
   reset does not say whether the dwarf drank water or booze.

## Validate against the real samples

The first real run's files are at (read-only, **do not copy into the repo**,
the repo is public and they are game data):

`C:\Users\wills\AppData\Local\Temp\claude\c--website-projects-df-automation\0c5c89af-0951-4758-9849-f28500e5fb50\scratchpad\series\`

Use `tl-20260918T213057Z-688464.jsonl` (10 samples, 23 citizens). It must
yield: `unit:192` has exactly one thirst reset, **at tick 12374606 - 1085 =
12373521**; every other citizen's thirst shows none. Report what the data says
about the hunger and sleepiness rates, including "not enough evidence" if that
is the honest answer. Encode small hand-written fixtures from what you learn;
**do not commit the real file**.

## Rules

- **Write as you go.** Commit on your branch after each milestone (registry,
  reset detection, rate refusal, aggregate, validation) and append to this
  file's write-up each time. Streams die on session limits routinely.
- Standard library only. No coordinates. **Never write an IP address,
  hostname or port into any committed file.**
- Keep `rate()`'s existing behaviour for `level` metrics unchanged.
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md` or `docs/TIMESERIES.md` (report contract changes).
  No em dashes in prose.

## Touched surfaces

`dfseries/**` and this handoff doc only.

## Done means

The real file gives exactly one exact thirst reset for `unit:192` at 12373521
and none for anyone else, `rate()` no longer returns a straddling slope for a
timer, each timer's rate is stated with its evidence or marked not
established, the per-dwarf-day aggregate works, the full suite passes (**446
passed / 1 skipped** right now, report before and after), and the write-up
says what the contract should now say.

## Write-up (executor, in progress)

Baseline confirmed before any change: `python -m pytest -q` at the repo root
gives **446 passed, 1 skipped**, matching the handoff.

**Read-only analysis of the real file** (a standalone script over
`tl-20260918T213057Z-688464.jsonl`, 10 samples, 9 intervals, 23 citizens per
metric = 207 citizen-intervals per metric), before writing any code, to
measure what to put in the registry rather than guess:

- `thirst_timer`: 206/207 intervals rose by exactly the tick gap. The one
  exception is `unit:192`, 33722 at `abs_tick` 12373406 to 1085 at
  `abs_tick` 12374606 -- reset dates to `12374606 - 1085 = 12373521`, exactly
  matching the handoff's required answer. No other citizen has a thirst
  reset. No anomalies (no interval rose more than the tick gap).
- `hunger_timer`: 207/207 intervals rose by exactly the tick gap. **Zero
  resets occurred for anyone in this window** -- nobody ate. So the
  between-reset rate (1/tick) has the same evidential weight as thirst's,
  but the reset-*dating* formula itself has never fired on a real hunger
  reset in this data. Registered as established by analogy; flagged in the
  registry evidence for a future run to confirm against a real hunger reset.
- `sleepiness_timer`: only 186/207 intervals matched "rose by exactly the
  tick gap". The other 21 are not stray noise, they are a real dynamic:
  while a citizen is awake the timer rises by exactly the tick gap (same
  signature as thirst/hunger), but during what is presumably sleep it
  *decreases* over one or more consecutive intervals, and not at a constant
  rate. `unit:192`: 49168 -> 46048 -> 23248 -> 448 across three consecutive
  1200-tick gaps, i.e. -2.6/tick, then -19.0/tick, then -19.0/tick. This
  confirms the handoff's suspicion exactly: it drains during sleep rather
  than snapping to zero, so there is no single between-reset rate and no
  exact-tick dating for it. Registered `rate_per_tick=None`, "not
  established".

**Milestone 1 committed**: `dfseries/metrics.py`, the metric-kind registry
(`kind_of`, `MetricKind`, `REGISTRY`), with the three timers' evidence
written up as above and unknown metrics defaulting to `LEVEL`. Tests in
`dfseries/tests/test_metrics.py`, 5 passed.
