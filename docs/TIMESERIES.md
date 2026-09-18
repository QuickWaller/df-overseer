# Time series: the contract between the sampler and the store

Status: **design, 2026-09-19, agreed with the user.** Nothing built yet. This
file is the **contract** two streams build against in parallel:

- the **sampler** (`scripts/dfhack/df-overseer-sampler.lua`), which runs
  inside the game and writes records;
- the **store** (`dfseries/`), which imports records into its own database and
  answers trend questions.

**Neither stream edits this file.** If either finds the contract wrong, it
reports the problem and the orchestrator changes it here, so the two sides
cannot drift apart silently.

## Why this exists

Before this, the project had a table shaped for observations
(`production_observation`) and **no system around it**: it had never held a
row, nothing wrote to it, `production.store.write_all(reset=True)` deleted it
along with the static graph on every re-extraction, and nothing understood
that the fort's tick can go **backwards** (a rollback on 2026-09-19 took it
from 235,668 to 213,622). Every trend the project has reasoned from so far,
including the exact thirst measurement (delta tick 6,303 = delta thirst
6,303), was taken by hand and survives only as prose.

## Design decisions, and why

1. **The game samples itself.** A DFHack `repeat` calls the sampler every N
   game days, the same mechanism as the autosave (`overseer-autosave`). This
   gives exact, evenly spaced ticks, runs whether or not any agent is running,
   and puts **no traffic on the DFHack command pipe**, which is what an
   external query wedged on 2026-09-19. It also does not depend on the agent
   loop, whose architecture is still undecided.
2. **Append-only JSONL on the VM, imported into a separate database.** The
   history must never share a lifecycle with the static graph. Re-extracting
   the graph must not be able to touch it.
3. **Every record carries a timeline id.** A tick alone is not a key once
   rollbacks exist. See "Timelines" below.
4. **Bounded reads only.** The sampler iterates specific vectors (units, item
   vectors, the job list). It **never scans map tiles**. This is a standing
   rule after the 2026-09-19 incident (`docs/TRAPS.md`).
5. **A failed read is recorded as a failure, never as zero.** Same rule as the
   silent-zero fix: a metric that could not be read carries `value: null` and
   an `error`, never `0`.

## The record format (version 1)

One JSON object per line, **one line per sample event** (not per metric), so a
single append is one atomic sample and a torn final line is detectable.

```json
{
  "v": 1,
  "timeline_id": "string, see Timelines",
  "timeline_start_abs_tick": 272606,
  "abs_tick": 273806,
  "cur_year": 30,
  "cur_year_tick": 273806,
  "wall_utc": "2026-09-19T09:30:00Z",
  "sampler_version": "string",
  "metrics": [
    {"subject": "fort", "metric": "population", "value": 23, "unit": "citizens"},
    {"subject": "fort", "metric": "deaths", "value": 0, "unit": "citizens"},
    {"subject": "unit:192", "metric": "thirst_timer", "value": 28922, "unit": "ticks"},
    {"subject": "item:DRINK", "metric": "stock", "value": null, "unit": "units",
     "error": "why it could not be read"}
  ]
}
```

- `abs_tick` is `cur_year * 403200 + cur_year_tick`, **always**. Never the bare
  tick, which resets every year (`production/schema.py`'s `abs_tick`).
- `value` is a number or `null`. **`null` requires `error`.** A number must
  never stand in for a failed read.
- `subject` is `fort`, `unit:<id>`, `item:<TYPE>`, or `job:<JobType>`.
  **No coordinates, ever** (`docs/PURPOSE.md` commitment #1).
- `metric` names are snake_case. The store must accept unknown metrics rather
  than drop them, since the sampler will grow.

## The starter metric set

| subject | metric | unit | note |
|---|---|---|---|
| `fort` | `population` | citizens | alive citizens |
| `fort` | `deaths` | citizens | dead citizens, cumulative |
| `unit:<id>` | `thirst_timer` | ticks | per citizen |
| `unit:<id>` | `hunger_timer` | ticks | per citizen |
| `unit:<id>` | `sleepiness_timer` | ticks | per citizen |
| `item:<TYPE>` | `stock` | units | fort-owned, stack units, for DRINK, food, SEEDS, PLANT, WOOD, BOULDER, BARREL, BUCKET at least |
| `job:<JobType>` | `queue_depth` | jobs | from the job list (a linked list: walk `.next`) |

Fort-owned means the existing `is_fort_owned` predicate in
`df-overseer-stocks.lua` (not `trader`, not `garbage_collect`, not
`removed`), reused rather than re-implemented.

## Timelines

A **timeline** is one continuous run of the game from one map load. The
sampler mints a new `timeline_id` **every time a map is loaded**, and keeps it
stable for that load. It also records the `abs_tick` at which that timeline
started, `timeline_start_abs_tick`.

**A rollback** is a load whose start tick is **earlier** than the latest tick
some previous timeline reached. When timeline B starts at tick T, every sample
from an earlier timeline A with `abs_tick > T` describes a future **that did
not happen** in the surviving history. Those samples are **superseded**, not
deleted: they are real observations of a discarded branch, and they may still
be worth something (today's discarded branch is where the thirst measurement
came from).

**The current lineage** is the newest timeline, plus, for each predecessor,
only its samples **at or before** the tick where its successor began. Trend
queries default to the current lineage. Asking across a superseded branch must
be an explicit choice.

## Where files live

On VM 103, append-only, **one file per timeline**, in a configurable
directory. The store imports lazily and idempotently: it tracks what it has
already read, and re-importing the same file must never duplicate a row. A
torn final line (the game stopped mid-write) is skipped and reported, never
parsed as a partial sample.

## Open, to be settled by the streams and reported back

- Sample interval. **Start at 1 game day (1,200 ticks)**, about two minutes of
  real time at the fort's 10 FPS; raise it if the cost is noticeable.
- Whether the store's database lives on the VM (next to the MCP server that
  will eventually serve trends) or is pulled to the workstation. Default: on
  the VM.
- Whether `production_observation` becomes a view onto the store or is
  retired. Until decided, `production.store` must at least **stop deleting
  it** on reset.
