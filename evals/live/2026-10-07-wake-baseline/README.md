# Wake metrics baseline, 2026-10-05 to 2026-10-07

First output of `python -m dfqueue.wake_metrics` (notebook N0, handoff
`handoffs/2026-10-07-wake-metrics.md`) on a read-only copy of the fort's
queue and runs stores, taken 2026-10-07 about 01:35 UTC. Numbers only.
`metrics.json` is the full published report (`wake_metrics/1`) and
`per_wake.jsonl` its per-wake rows, kept because the runs store keeps only
its last 500 rows.

Volume is small and unrepresentative: 24 finished wakes over 3 calendar days
(25 runs, one still running at copy time), hand-run `--once` sweeps under an
operator hold, not the service cadence. Read these as a baseline for the
instrument, not a rate. Only 3 wakes carry a transcript (run-0022, run-0023,
run-0024), so every round, read and tool figure rests on one wake per role.

## Waste, by role

| role | wakes | at risk | M1 text | M1 struct | M1 wide | M2 | M3 | R | R per at-risk wake (90% interval, by sweep) |
|---|---|---|---|---|---|---|---|---|---|
| architect | 6 | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 0.00 |
| quartermaster | 10 | 9 | 0 | 7 | 7 | 0 | 2 | 2 | 0.11 (0.00 to 0.25) |
| overseer | 7 | 4 | 0 | 0 | 0 | 5 | 0 | 5 | 1.25 (1.00 to 1.67) |
| consultant | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none |
| all | 24 | 18 | 0 | 7 | 8 | 5 | 2 | 7 | 0.33 |

R (the primary count) is M1 text, M3 and M2 only: 7 events, all repeat
defers (5) and duplicate rejections (2). M1 text finds none, see below.
Episodes: overseer 5 events in 2 episodes, quartermaster 2 in 2 (1.75 events
per episode overall). `m3_cross_role` is 0.

## Per wake

| role | cost mean (USD) | killed | rounds | rounds to first write | orientation reads | pass rate |
|---|---|---|---|---|---|---|
| architect | 0.048 (4 costed) | 2 (both 600 s timeouts, no output) | 11 (1 wake) | 9 | 25 | 0.17 |
| quartermaster | 0.048 | 0 | 8 (1 wake) | 5 | 19 | 0.00 |
| overseer | 0.060 | 0 | 12 (1 wake) | 7 | 15 | n/a |
| consultant | 0.042 | 0 | no transcript | | | n/a |

Total cost over 22 costed wakes 1.13 USD, mean 0.051. Redundant re-reads:
0 of 62 read calls in the 3 transcribed wakes (the rate is an upper bound
by the spec; the fort was paused). Tokens in those 3 wakes: input 169k,
output 108k, reasoning 101k, cache read 1.74M.

## Power projection (red-team finding 2)

R per at-risk wake 0.33, 1.75 events per episode, 6 at-risk wakes per
active day. A 50% cut in R at 5% one-sided and 80% power needs about 203
at-risk wakes per arm after inflating for episode size, about 68 days at
this volume. Treat as a floor: the sample is one operator-held burst.

## Per-tool usage (from the 3 transcripts)

Distinct tools called: architect 12, quartermaster 14, overseer 15.
Allowlisted tools not called in them: architect 42, quartermaster 13,
overseer 67. Three wakes cannot justify a cut; this is the pipeline, run it
again over more transcripts. Wire names mapped to allowlist ids with 0
unmapped calls.

## Validation against hand labels (13 proposals, 24 rulings of 2026-10-05..07)

| metric | flagged | true | correct | precision | recall |
|---|---|---|---|---|---|
| M1 text (server rule) | 0 | 5 | 0 | undefined | 0.00 |
| M1 struct | 7 | 5 | 4 | 0.57 | 0.80 |
| M1 wide | 8 | 5 | 4 | 0.50 | 0.80 |
| M3 | 2 | 2 | 2 | 1.00 | 1.00 |
| M2 | 5 | 5 | 5 | 1.00 | 1.00 |

The server's text rule never fires on the window: the Quartermaster
paraphrases each wake. It is not a usable primary for repeats; use M2 and M3
as R's reliable parts and M1 struct (same signal and operator, mostly the
same precondition landmarks, fitted on this window, so optimistic) or a
hand-labelled M1 as the repeat count. Labels and their reasons are in
`dfqueue/tests/fixtures/wake_window_2026_10_05.json`.
