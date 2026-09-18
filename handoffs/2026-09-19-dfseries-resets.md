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

**Milestone 2 committed**: `trend.resets()` (dataclasses `ResetEvent`,
`Anomaly`, `ResetsResult`) and `trend.rate()`'s refusal to straddle a
reset.

- `resets()` walks consecutive non-null readings. For an established-rate
  metric it applies the handoff's three-way test (`v1 == expected`: no
  reset; `v1 < expected`: an `EXACT_TICK` event dated to `t1 - v1/rate`;
  `v1 > expected`: an `Anomaly`, never folded into `events`). For an
  unestablished metric there is no "expected" to compare against, so only
  an outright decrease (`v1 < v0`) is reported, as `INTERVAL_BOUNDED`
  (`abs_tick=None`); a rise produces neither an event nor an anomaly --
  there is no basis to call it either way. A `LEVEL` metric always returns
  empty `events`/`anomalies`.
- `rate()` now branches on `metrics.kind_of(metric).kind`. `LEVEL` (and
  anything unregistered) is byte-for-byte the old behaviour, now labelled
  `segment="endpoint"`. For `RESETTING_COUNTER`, it calls `resets()` over
  the same window first: no reset found means the endpoint slope is safe
  and returned as-is (`segment="endpoint"`); a reset found means the raw
  endpoint slope is **never** returned -- instead it recomputes from the
  last reset's tick (or its interval's end, for an interval-bounded event)
  onward, labelled `segment="between_reset"`, or `UNAVAILABLE` with a
  reason naming the reset and pointing at `resets()` if fewer than two
  readings remain after it.
- One design note worth flagging back to the contract: a gap can contain
  more than one reset (e.g. two drinks between two samples 1,200 ticks
  apart); the three-way test only ever dates **the last** reset in a gap,
  because two points cannot distinguish multiple resets within them. This
  matches the handoff's own wording ("the last one happened at exactly
  `t1 - v1`") but is worth stating explicitly in `docs/TIMESERIES.md` if
  it does not already say so -- see "What the contract should now say"
  below.
- Tests: `dfseries/tests/test_resets.py`, 11 new tests, hand-written
  fixtures for each of the three named dynamics (an exact-tick thirst
  reset dated to 12373521 exactly as the real data will confirm, a
  no-reset thirst citizen, an established-rate anomaly, an
  interval-bounded sleepiness decrease, a sleepiness rise that is neither
  event nor anomaly, a resets()-on-level no-op, and four rate() cases:
  refused-across-a-reset, between-reset-slope-returned,
  no-reset-endpoint-labelled, level-unchanged).
- Full suite: **462 passed / 1 skipped** (was 446/1 before this stream;
  +5 registry tests, +11 resets/rate tests).

**Milestone 3 committed**: `dfseries/aggregate.py`,
`dwarf_day_reset_rate()` and the `DwarfDayRate` dataclass -- deliverable 4.
Aggregates `trend.resets()` across every `unit:*` subject for one metric in
a window; `dwarf_days_observed` is the sum, per subject, of that subject's
own last-usable-reading-minus-first-usable-reading tick span divided by
`TICKS_PER_DAY` (1200, duplicated from `production/cover.py.TICKS_PER_DAY`
rather than imported, so `dfseries` keeps no runtime dependency on
`production/` -- consistent with `dfseries/schema.py`'s "the two databases
must never share a lifecycle"). A subject with only one reading contributes
zero dwarf-days, never a full day. `events_per_dwarf_day` is `None`, never
a division by zero, when no dwarf-days were observed. `thirst_timer` gets
the special label "drinking events per dwarf-day"; every other metric gets
a generic `"{metric} reset events per dwarf-day"` label so the function
never silently mislabels a metric nobody has thought about yet. Tests in
`dfseries/tests/test_aggregate.py`, 4 passed (three citizens with one
reset between them, an empty-database no-crash case, an
interval-bounded-only case on `sleepiness_timer`, and a window-respecting
case proving a reset outside `[start, end]` neither counts nor extends
`dwarf_days_observed`). Full suite: **466 passed / 1 skipped**.

**Milestone 3b committed**: CLI wiring, `dfseries/cli.py` gains `resets`
and `dwarf-day` subcommands, and `rate` now prints its `segment` and
`metric_kind`, plus the refusal `reason` when there is one, so a human
running the tool against the real database sees the same refusal a caller
would get. 4 new tests in `dfseries/tests/test_cli.py`. Full suite:
**469 passed / 1 skipped**.

**Milestone 4: real-data validation (read-only, not committed).** Ran the
full pipeline (`store.connect` -> `importer.import_file` ->
`aggregate._unit_subjects` -> `trend.resets` per subject ->
`aggregate.dwarf_day_reset_rate`) against
`tl-20260918T213057Z-688464.jsonl` from a throwaway temp database, via an
ad-hoc script, never committed and never copying the file's content into
the repo. Results:

- **Thirst**: exactly one reset, `unit:192` at `abs_tick 12373521`, matching
  the handoff's required answer exactly (`12374606 - 1085`). All 22 other
  citizens: zero events, zero anomalies. `dwarf_day_reset_rate(conn,
  "thirst_timer")` over the whole file: `event_count=1`,
  `exact_tick_events=1`, `subjects_observed=23`,
  `dwarf_days_observed=207.0` (23 citizens * 9 ticks-of-1200 each / 1200 =
  23*9=207 dwarf-days, since every citizen has readings at all 10 sample
  points spanning 9 gaps), `events_per_dwarf_day=1/207=0.004831` --
  roughly one drink reset caught per 207 dwarf-days of observation in this
  9-day window. That figure is not itself a claim about how often dwarves
  actually drink (the window is short and this is the demand side of a
  single reset event, not a rate anyone should generalise from ten
  samples) -- it is reported here only to prove the calculator works
  end-to-end on real numbers.
- **Hunger**: zero resets, zero anomalies, for every citizen in this
  window. This matches the registry entry: the between-reset rate (1/tick)
  is as well evidenced as thirst's (207/207 exact), but this window never
  produced a real hunger reset to test the exact-tick dating formula
  against. Honest answer: **hunger's between-reset rate is established,
  its reset-dating formula is not yet tested against a real reset.**
- **Sleepiness**: 20 interval-bounded events, 0 exact-tick, 0 anomalies
  (anomalies are only possible for an established-rate metric, and
  sleepiness has none). This matches a hand count of outright decreases
  in the raw file exactly (20). Honest answer: **not enough evidence for
  a between-reset rate** -- the data actively contradicts a single fixed
  rate (the sleep-drain segments measured at -2.6/tick then -19.0/tick for
  the same citizen back to back), so "not established" is not a
  placeholder here, it is what the data shows.

## What the contract (`docs/TIMESERIES.md`) should now say

Not written there by this stream (out of touched surfaces); reporting back
per the handoff's instructions.

1. **A new section belongs next to "Timers reset: a rate across a reset is
   meaningless"**, saying that the exact-tick dating property is per-metric,
   not automatic for every `*_timer`: it must be measured (as this stream
   measured thirst and hunger) before it is used, and a metric can be a
   resetting counter with **no** established rate (sleepiness_timer) --
   that is a valid, expected state, not a bug to fix later.
2. **The starter metric set table** (`hunger_timer`, `sleepiness_timer`
   rows) could grow a `kind` or `reset behaviour` column pointing at
   `dfseries/metrics.py`, so a reader does not have to already know to look
   there.
3. **Worth stating explicitly**: a single two-point gap can contain more
   than one reset (two drinks 1,200 ticks apart, say); the exact-tick
   formula only ever dates the *last* reset in a gap, which the handoff's
   own wording already implies ("the last one happened at exactly
   `t1 - v1`") but which the contract does not currently spell out as a
   limit.
4. **`sleepiness_timer`'s dynamic is worth a line of its own**: it is not
   simply "a resetting counter with an unknown rate" in the same sense
   hunger might turn out to be once more data exists -- the real data shows
   it *decreases* over multiple consecutive intervals at inconsistent rates
   while (presumably) asleep, then rises again at exactly 1/tick while
   awake. That is a different shape from "counts up, snaps to a low value
   on an event", and a future stream investigating sleep mechanics should
   know that going in rather than rediscover it.

## Status: done

All four deliverables built (`dfseries/metrics.py`, `trend.resets()`,
`rate()`'s refusal, `aggregate.dwarf_day_reset_rate()`), CLI wired, real
file validated read-only with the exact required result, hand-written
fixtures encoded in `dfseries/tests/test_resets.py` and
`dfseries/tests/test_aggregate.py`. Test count: **446 passed / 1 skipped
before -> 469 passed / 1 skipped after** (+23: 5 registry, 11 resets/rate,
4 aggregate, 3 CLI).
