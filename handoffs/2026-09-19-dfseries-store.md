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

## Write-up

**Status: done.** Test count: **415 passed / 1 skipped before, 446 passed /
1 skipped after** (26 dfseries tests + 3 production/store.py tests + 2
dfseries CLI tests = 31 new). Commits on this branch, in order: package
skeleton (schema/store/timeline/importer + 9 importer tests), rollback tests
against the real 213622/235668 figures (5 tests), the trend layer (7 more
tests, one of which found and fixed a real edge case, see below), the
`production/store.py` fix (3 tests), the CLI (2 smoke tests).

### Package layout

```
dfseries/
  __init__.py
  schema.py     DDL: timelines / sample_events / sample_metrics / imported_files.
                Open-vocabulary subject/metric on purpose (no CHECK
                constraint), unlike production/schema.py's closed
                STATUS_VALUES/OBSERVATION_METRICS -- the contract requires
                accepting metrics the store has never seen.
  store.py      connect()/schema bootstrap, upsert_timeline, insert_event
                (returns None on a duplicate (source_file, source_line)),
                insert_metric, recompute_superseded, import progress
                (get_progress/set_progress). Follows dfqueue/store.py's own
                precedent (WAL, Row factory, schema_version check, with
                conn: transactions).
  timeline.py   Rollback detection and lineage computation. recompute_lineage()
                orders every known timeline by first_wall_utc (not tick --
                that's exactly what a rollback breaks), sets each
                predecessor's cutoff_abs_tick to its immediate successor's
                start tick, and recomputes every sample_events.superseded
                flag from that.
  importer.py   import_file() / import_files(). One JSONL line = one sample
                event = one row in sample_events, one row per metric in
                sample_metrics.
  trend.py      series() / latest() / rate() / cover_rows(), all defaulting
                to lineage="current".
  cli.py        argparse: import / timelines / series / latest / rate.
  tests/        test_importer.py, test_timeline.py, test_trend.py,
                test_cli.py.
```

Two tables carry the per-event fields once (`sample_events`) and the
per-metric fields separately (`sample_metrics`), rather than denormalising
event fields onto every metric row -- a 4-metric sample event is 1 event
row + 4 metric rows, not 4 fully-duplicated rows.

### Rollbacks and nulls

**Rollback detection** orders timelines by `first_wall_utc` (parsed via
`datetime.fromisoformat`, `Z` treated as `+00:00`), falling back to
insertion order (`rowid`) only when `wall_utc` is missing -- ticks cannot be
the ordering key since a rollback is defined by tick order breaking. Each
non-newest timeline's `cutoff_abs_tick` is set to its *immediate* successor's
`start_abs_tick` (not the newest timeline's), matching the contract's
singular "its successor". `recompute_superseded()` then marks
`sample_events.superseded = 1` wherever `abs_tick > cutoff_abs_tick`. This
runs as a full recompute after every import call (cheap at one event per
game day) rather than incremental patching, so it stays correct regardless
of import order once `wall_utc` is present.

Tested against the contract's own real figures: timeline A samples
213622/220000/235668, timeline B starts at 213622 and runs to 250000. A's
213622 sample stays current (superseded=0, "at or before" the cutoff); its
220000 and 235668 samples are marked superseded=1 and **kept** (row count
unchanged, 3 rows for A both before and after); B's samples are never
superseded. `lineage="all"` reaches the superseded rows explicitly.

**A real edge case found while writing the rollback test, not anticipated
in the contract**: at the exact tick a successor timeline begins, the
predecessor's boundary sample ("at or before" -- included) and the
successor's own first sample (part of "the newest timeline, full" --
included) can both land in the current lineage for the same
subject/metric/abs_tick. `docs/TIMESERIES.md` doesn't say which should win
if they disagree. Resolved in `trend.series()`: on a tie, the row belonging
to the current tip timeline (no successor) wins; `lineage="all"` is
unaffected and returns both. Documented in `trend.py`'s module docstring as
a resolved-but-open contract question -- flagging it here rather than
letting it sit silently in code, per this stream's own instructions.

**Nulls**: `sample_metrics.value` is a nullable REAL column; the importer
writes exactly what the record carries, never substituting 0 and never
dropping the row. `trend.series()` returns `value: None` with `error` set
unchanged. `trend.rate()` excludes null-valued rows from the slope
calculation (can't be a point on a line) but reports `skipped_nulls`
separately from `sample_count` (the non-null rows actually used). A window
of only-null rows returns `status="unavailable"` with a reason, same
contract `production/cover.py.depletion_rate_per_day` already applies for
"fewer than two points": never a wiki-style guess for a data gap.

### Trend API

```python
trend.series(conn, subject, metric, *, start_abs_tick=None, end_abs_tick=None, lineage="current") -> list[dict]
    # [{"abs_tick", "value", "unit", "error", "timeline_id", "superseded"}, ...] oldest first

trend.latest(conn, subject, metric, *, lineage="current") -> dict | None
    # same row shape as series()[-1], or None

trend.rate(conn, subject, metric, *, start_abs_tick=None, end_abs_tick=None, lineage="current") -> RateResult
    # RateResult(status, value, sample_count, tick_span, skipped_nulls, reason)
    # value = (last.value - first.value) / (last.abs_tick - first.abs_tick)
    # over the non-null rows in the window; unavailable below two distinct ticks.

trend.cover_rows(conn, subject, metric, *, start_abs_tick=None, end_abs_tick=None, lineage="current") -> list[dict]
    # [{"subject_id", "metric", "abs_tick", "value", "unit"}, ...], nulls excluded,
    # proven directly against production.cover.depletion_rate_per_day in
    # dfseries/tests/test_trend.py (not a stub -- the real function, real values).
```

`lineage="current"` (default) or `lineage="all"`; anything else raises
`ValueError` rather than silently falling back to one of the two.

The thirst check from the handoff: two samples of a citizen who did not
drink (`value` 20000 at tick 213622, `value` 26303 at tick 219925, matching
the register's 6303-tick delta) give `rate.value == 1.0` exactly,
`tick_span == 6303`, `sample_count == 2`. Verified both as a unit test and
by hand through the CLI (`dfseries/cli.py rate`), which printed `+1.000000
per tick, over 6303 ticks, 2 sample(s) used, 0 null reading(s) skipped`.

### The `production/store.py` fix

`write_all(reset=True)` used to `DELETE FROM production_observation` in the
same loop as the static graph tables. The fix removes
`production_observation` from that loop's table list; `reset=True` still
clears `production_node`/`production_class`/`material_reaction_product`/
`production_process`/`production_flow`/`production_attribute` (idempotent
re-extraction is preserved), but observation history now survives every
reset. New observation rows passed to `write_all` are appended, not used to
replace what's already there -- `write_all` has no notion of "this
observation already exists" (no natural unique key across a re-run), so
repeated calls accumulate history, which is the correct behaviour for a
table meant to hold a growing time series. Three tests in
`production/tests/test_store.py` cover: reset preserves existing
observations while still resetting the graph tables, `reset=False` behaves
as before, and repeated writes accumulate rather than overwrite.

This only patches the leak; it does not decide `docs/TIMESERIES.md`'s open
question ("whether `production_observation` becomes a view onto the store or
is retired"). That question is explicitly out of scope for this stream and
still open.

### What a VM deployment would need

1. **A directory for the sampler's JSONL output** on VM 103, one file per
   `timeline_id` per the contract ("Where files live"). This stream never
   touched the VM; the sampler stream (`handoffs/2026-09-19-sampler.md`)
   owns creating that directory and writing to it.
2. **A dfseries database path.** `store.default_path("uniboslan")` resolves
   to `dfseries/uniboslan.series.sqlite3` next to the package, mirroring
   `production/store.py`'s and `dfqueue/store.py`'s own `default_path()`
   convention. Added `dfseries/*.sqlite3*` to `.gitignore` in this stream
   (same pattern as the existing `dfqueue/*.sqlite3*` and
   `production/*.sqlite3*` lines), so the live database and its WAL/SHM
   sidecar files never land in git.
3. **A periodic import.** Nothing in this package schedules itself --
   `python -m dfseries.cli import <db> <file1> [<file2> ...]` is a single
   idempotent pass, safe to run from cron/systemd-timer/repeat on any
   cadence, or just after the sampler writes. Multiple files should be
   passed **in real-world chronological order** (e.g. sorted by mtime) when
   `wall_utc` might be absent from a record; with `wall_utc` present, the
   contract's normal case, import order doesn't affect the resulting
   lineage (proven in `test_timeline.py::
   test_import_order_does_not_matter_when_wall_utc_is_present`).
4. **Nothing new to install.** Standard library only (`sqlite3`, `json`,
   `argparse`, `dataclasses`, `datetime`, `pathlib`), same venv as the rest
   of the repo.
5. **Not yet wired to anything live.** No MCP tool, no dfmcp exposure, no
   scheduled job -- this stream built the store and its read API, not its
   integration into the running system. That's the natural next step once
   the sampler stream lands a real JSONL file to import against (the
   handoff's own words: "proving the store against it is the next step, not
   yours").

### Anything wrong (or worth a second look) in the contract

- **The boundary-tie case above** (predecessor's "at or before" sample vs.
  successor's own first sample, same subject/metric/abs_tick): not wrong,
  just underspecified. Worth a one-line addition to `docs/TIMESERIES.md`
  "Timelines" saying which wins, so a second implementation doesn't have to
  rediscover this and possibly choose differently.
- **`wall_utc` is load-bearing for correctness, not just informational.**
  The contract lists it as a field in the record format but doesn't say
  explicitly that it is *the* ordering key for rollback detection (as
  opposed to, say, import order or a monotonic sequence number the sampler
  could also emit). Recommend making that explicit in the contract, since a
  future importer (or a rewrite of this one) could otherwise reasonably
  assume tick order or file order is enough and get rollback ordering wrong
  on a clock skew or an out-of-order backfill.
- **No contract statement on clock skew or backward wall-clock jumps.** If
  the VM's clock itself were ever corrected backwards between two timelines,
  `first_wall_utc` ordering could misorder them. Not observed, not a
  blocker, just noted as a real (if narrow) failure mode of the wall-clock
  approach the contract's own design implies.
- **`production/schema.py`'s `OBSERVATION_METRICS` is closed and does not
  include `thirst_timer`/`hunger_timer`/`sleepiness_timer`**, three of the
  contract's own starter metrics. This is not a bug in this stream's work
  (`cover_rows()` never writes into `production_observation` or calls
  `schema.validate_observation`; it only shapes rows for
  `cover.depletion_rate_per_day`, which does not check the metric
  vocabulary), but it means those three metrics could never be written into
  `production_observation` today even after `docs/TIMESERIES.md`'s open
  question about that table is settled. Worth tracking whoever resolves
  "does `production_observation` become a view onto dfseries" also revisits
  that vocabulary.
- Everything else in the contract (record shape, `abs_tick` formula, the
  four `subject` prefixes, null-requires-error, unknown-metrics-accepted)
  matched the build cleanly; no other surprises.
