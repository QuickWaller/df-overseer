# Handoff: `dfseries`, the time-series store and trend layer

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.** A
parallel live stream builds the in-game sampler
(`handoffs/2026-09-19-sampler.md`); **you share one contract with it,
`docs/TIMESERIES.md`, and must not edit that file.** If the contract is wrong,
report it.

Read `CLAUDE.md`, then **`docs/TIMESERIES.md` in full**, then
`production/schema.py` and `production/store.py`, then `production/cover.py`
(the one existing consumer of observation-shaped rows), then this.

## Deliverable

A new package, **`dfseries/`**. Named with the `df` prefix on purpose, for the
same reason as `dfmcp` and `dfqueue`: a bare generic name risks shadowing
something on `sys.path`.

1. **An importer.** Reads contract-format JSONL files. **Idempotent**:
   importing the same file twice, or a file that has grown since last time,
   never duplicates a row. **A torn final line is skipped and reported**,
   never parsed as a partial sample. A line with an unknown `v` is refused and
   reported, not guessed at. Unknown **metrics** are accepted and stored.
2. **Its own SQLite database**, separate from the production graph's. The
   history must never share a lifecycle with the static graph.
3. **Timeline handling**, exactly as the contract's Timelines section defines
   it: detect rollbacks, mark the superseded samples of an earlier timeline
   **without deleting them**, and compute the **current lineage**.
4. **A trend layer**, defaulting to the current lineage:
   - a subject's series for a metric over a tick window;
   - the latest value;
   - **a rate over a window**, reporting the number of samples and the tick
     span it rests on, so a rate from two points is visibly weaker than one
     from forty;
   - rows shaped for `production/cover.py`, so the existing cover calculator
     can consume real history.
5. **A small CLI** for a human to run a report.

## The fix to `production/store.py`

`write_all(reset=True)`, the default, deletes `production_observation` along
with the static graph tables, so every re-extraction erases history. **Stop
that**: reset must clear only the static tables. Add a test proving
observations survive a reset. This is the only change you make outside
`dfseries/`.

## Tests that matter more than coverage

- **The rollback case, from real figures.** Timeline A samples from tick
  213,622 to 235,668; timeline B starts at 213,622 and runs on. A's samples
  after 213,622 are superseded, still stored, excluded from the default
  lineage, and reachable when asked for explicitly. **A rate computed across
  the rollback without lineage handling would be nonsense, so write the test
  that proves the default query does not do that.**
- **`null` stays `null`.** A metric recorded as `null` with an `error` is never
  imported as `0` and never silently dropped; a rate over a window containing
  nulls says how many it skipped.
- **Idempotency**: import, grow the file, import again, count rows.
- **A torn line** is skipped and reported.
- **The thirst check**: two samples of a citizen who did not drink give a
  thirst rate of exactly 1 per tick.

Write fixtures by hand in the contract's format. The real sample file will
exist on the VM once the sampler stream lands; proving the store against it is
the next step, not yours.

## Rules

- No new runtime dependency beyond the standard library.
- No coordinates anywhere.
- **Never write an IP address, hostname or port into any committed file.**
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/` or
  `handoffs/INDEX.md`. No em dashes in prose.

## Touched surfaces

`dfseries/**` (new), `production/store.py` and its test for the reset fix, and
this handoff doc. **Not** `docs/TIMESERIES.md`, `scripts/`, or any other file
under `production/`.

## Done means

The package imports contract files idempotently, handles rollbacks per the
contract, answers the trend queries above, feeds `cover.py`-shaped rows,
`production.store` no longer destroys history, the full suite passes (**415
passed / 1 skipped** right now, report before and after), and the write-up says
what a deployment on the VM would need.
