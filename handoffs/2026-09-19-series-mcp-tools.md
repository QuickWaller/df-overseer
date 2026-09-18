# Handoff: serve the fort's history to agents over MCP

Date: 2026-09-19. **Offline build stream. No VM, no SSH, no deploy.**

Read `CLAUDE.md`, then `docs/TIMESERIES.md`, then `dfseries/` in full
(including the reset-aware API added by
`handoffs/2026-09-19-dfseries-resets.md`, read its write-up), then
`dfmcp/doctrine_tools.py` **in full**, which is the pattern you follow, then
this.

## The goal

The fort now records its own history (`dfseries`), and it imports on the VM
automatically (`handoffs/2026-09-19-dfseries-auto-import.md`). **No agent can
see any of it.** Build the read-only MCP tools that let one.

## Deliverable

Native tools in a new `dfmcp/series_tools.py`, served **exactly the way
`doctrine_tools.py` is**: hand-written `NativeTool`s with explicit JSON
schemas, merged via `load_registry(native_tools=...)`, enforced through the
one `Roster.check` boundary, routed by `dfmcp/server.py`'s generalised
native-tool branch. **One boundary, not a second permission path.**

The minimum set, each wrapping the `dfseries.trend` function of the same
purpose rather than re-implementing it:

- **the timelines**, marking which is current and which are superseded;
- **a series** for a subject and metric over a tick window;
- **the latest value**;
- **a rate over a window**;
- **reset events** for a resetting timer, and the **fort-level events per
  dwarf-day** aggregate (drinking events, for thirst).

Name the ids to match the registry's conventions (`doctrine.get` is the
precedent) and say what you chose.

## What the output must never lose

The store was built to refuse confident nonsense. **The tools must carry
every qualifier through to the agent, unflattened**, because an agent reading
a bare number is exactly how this project's past errors propagated:

- every rate carries its **sample count, tick span and skipped nulls**;
- every output states the **metric kind it assumed** (level or resetting
  counter) and, for a counter, whether reset times are **exact or
  interval-bounded**;
- an `unavailable` result carries its **reason**, and is never rendered as a
  number;
- a query that reached a **superseded** timeline says so;
- **a `null` reading is never rendered as `0`.**

Write a test for each of those, through the real registry and roster, not just
against the functions.

## Decisions you must make and state

- **Which roles get which tools.** The quartermaster role (if enabled) owns
  inventory and production trends by agreed design; the overseer arbitrates;
  the consultant fact-checks. Read `agents/*/role.md` and choose deliberately,
  per role, with a reason, as the `get_doctrine` stream did.
- **`knowledge_scope`.** This is live fort state read by the game itself, which
  is a different case from doctrine's curated corpus. Read how `roles.py` uses
  the field and choose; `player_derivable` is plausible because every metric is
  something a player can see in-game, but say why.
- **The database path**: configurable, read from the environment like
  `MCP_SERVER_DOCTRINE_PATH`, defaulting to whatever path the auto-import stream
  chose (read its write-up); **fail loudly if the database is absent**, never
  return empty history as though the fort had none.

## Rules

- **Write as you go.** Commit on your branch after each milestone and append
  to this file's write-up each time.
- Read-only: `.mutates` is `False`.
- No coordinates. **Never write an IP address, hostname or port into any
  committed file.**
- Do **not** write `Working.md`, `decisions/DECISIONS.md`, `memory/`,
  `handoffs/INDEX.md` or `docs/TIMESERIES.md`. No em dashes in prose.

## Touched surfaces

`dfmcp/series_tools.py` (new), its tests, minimal wiring in `dfmcp/server.py`
and test fixtures that load the registry, `agents/*/tools.yaml`,
`infra/local.example.env` (one new path variable), and this handoff doc.
**Not** `dfseries/`.

## Done means

The tools are reachable through the real registry and roster, every qualifier
above survives to the agent and is tested, the role and scope choices are
stated with reasons, the full suite passes (report before and after), and the
write-up says exactly what a deploy needs.

## Write-up (executor, done)

Baseline confirmed before any change: `python -m pytest -q` at the repo root
gives **470 passed, 1 skipped**, matching the handoff (and matching
`handoffs/2026-09-19-dfseries-resets.md`'s own "done" count, since that
stream merged just before this one started). `dfseries/metrics.py` and
`dfseries/aggregate.py` were present in the worktree already, confirming the
merge had landed.

**Milestone 1 committed**: `dfmcp/series_tools.py`, all six tools defined
(`series.timelines`, `series.get`, `series.latest`, `series.rate`,
`series.resets`, `series.dwarf_day_events`), each wrapping exactly one
`dfseries` function (`timeline.lineage_summary`, `trend.series`,
`trend.latest`, `trend.rate`, `trend.resets`,
`aggregate.dwarf_day_reset_rate` respectively) with a hand-written
`NativeTool`/schema pair, following `doctrine_tools.py`'s pattern exactly
(a `_DESCRIPTIONS` dict keyed by tool id, `NativeTool.describe()` dispatching
into it, real argument validation independent of the JSON schema's
`additionalProperties: false`). Module docstring states and justifies every
design decision up front (see below for the summary). Smoke-tested by hand
against a fixture database before writing formal tests.

**Milestone 2 committed**: role grants. `agents/overseer/tools.yaml` and
`agents/consultant/tools.yaml` each grant the full six-tool set under
`read:`; `agents/architect/tools.yaml` gets a `series.*` wildcard `deny`
with a stated reason; `agents/quartermaster/tools.yaml` (disabled role)
grants the full set too, so enabling that role later needs no allowlist
decision. Verified against the real `load_registry`+`load_roster` (not just
read by eye): overseer and consultant see `allowed=True` on all six ids,
architect sees `allowed=False` on all six.

**Milestone 3 committed**: wiring. `dfmcp/server.py` imports
`series_tools`, `ServerConfig` gains `series_db` (env `MCP_SERVER_SERIES_DB`,
default `series_tools.DEFAULT_SERIES_DB_PATH`), `build_mcp_server`/`_serve`/
`main()` thread it through, and the native-tool dispatch branch in
`_handle_call_tool` routes `series.*` ids to `series_tools.call` and catches
`SeriesToolError` the same way `QueueToolError`/`DoctrineToolError` are
already caught. This immediately broke five **existing** test fixtures
(`test_auth.py`, `test_roles.py`, `test_server.py`, `test_tools.py`,
`test_doctrine_tools.py`'s `TestRosterWiring`) that build "the real
registry" via `load_registry(native_tools=...)` without merging
`series_tools.NATIVE_TOOLS` in: once `agents/overseer/tools.yaml` and
`agents/consultant/tools.yaml` reference `series.*` ids, `roles.py` rule 1
(an allowlist id must exist in the registry) refuses to load the real
roster at all. All five fixtures updated to merge `SERIES_NATIVE_TOOLS` in,
matching how they already merge `DOCTRINE_NATIVE_TOOLS`. `dfmcp/tests`
ambient (no pinned `mcp` SDK): **162 passed, 1 skipped** (server.py's own
transport tests skip cleanly, by design, without the SDK). Repo-wide:
**470 passed, 1 skipped**, unchanged, since `test_series_tools.py` did not
exist yet.

**Milestone 4 committed**: `dfmcp/tests/test_series_tools.py`, 59 new tests,
transport-free (imports nothing from `mcp`, same style as
`test_doctrine_tools.py`, so it runs ambiently). Fixtures are hand-written
JSONL records imported through the real `dfseries.importer.import_file`
(never hand-inserted rows), covering: a two-citizen-plus-one thirst
scenario (one exact-tick reset, one steady no-reset citizen, one
single-reading citizen); a real rollback (two timelines, a superseded
sample, a resolved boundary tie) built to `docs/TIMESERIES.md`'s own
definition; a single failed read (`value: null`, `error` set); and a
`sleepiness_timer` decrease to exercise the interval-bounded reset path.
Every qualifier the handoff named is asserted explicitly:

- `series.rate`'s `sample_count`/`tick_span`/`skipped_nulls` survive on
  both a measured and an unavailable result.
- Every metric-bearing tool's output states `metric_kind`
  (`level`/`resetting_counter`), and, where relevant, `rate_per_tick` and
  `reset_to_zero_verified`.
- `series.resets`' `unit:192` reset dates to `abs_tick 115` in this
  fixture's 0-based tick space -- the same arithmetic
  (`handoffs/2026-09-19-dfseries-resets.md`'s `12374606 - 1085 = 12373521`)
  applied to this fixture's own numbers (`1200 - 1085 = 115`), a direct
  cross-check against `dfseries`' already-validated result, not a
  freestanding assertion.
- `sleepiness_timer`'s reset is `interval_bounded` with `abs_tick: None`,
  never a guessed tick, for a metric with no established rate.
- `series.rate` on `unit:192` (a reset in the window) returns `status:
  "unavailable"`, `value: None`, and a non-empty `reason` -- asserted
  directly against the text form too (`'value="null"' in text` and
  `'value="0"' not in text`), not just the structured dict.
- The rollback fixture's `series.get` with `lineage="current"` returns
  `superseded_count == 0` and resolves the `abs_tick=1000` boundary tie in
  favour of the tip timeline (`t2`); `lineage="all"` returns
  `superseded_count == 1` and surfaces the discarded `t1` row explicitly.
- The failed-read fixture's `value` is asserted `is None` (never `== 0`),
  in both `structuredContent` and the XML text (`'value="null"'` present,
  `'value="0"'` absent).
- `series.dwarf_day_events`'s `event_count`/`dwarf_days_observed` are the
  first two XML attributes (asserted by string position, not just
  presence), and a `caution` field appears whenever `event_count` is below
  the module's threshold (5); a database with no `unit:*` subjects for the
  metric gets `events_per_dwarf_day: None` and `events_per_dwarf_day_status:
  "unavailable"`, never `0`.
- `TestDatabaseAbsent` proves the guard is real, not just that it raises:
  after a refused call against a missing path, `missing.exists()` is still
  `False` -- `dfseries.store.connect` was never given the chance to create
  an empty database there.
- `TestRosterWiring` (parametrised over all six ids) proves overseer and
  consultant hold every tool, architect holds none, no tool `mutates` or is
  `sole_writer_only`, and every tool's `knowledge_scope` is
  `"player_derivable"` -- never absent (unlike `doctrine.get`, which reads
  no live fort state at all) and never `"omniscient"` (which would make
  `roles.py` rule 7 refuse it to every role, including the sole writer,
  defeating the whole point of this stream).

`dfmcp/tests` ambient after this file: **221 passed, 1 skipped** (+59).
Repo-wide: **529 passed, 1 skipped** (+59 from 470).

**Milestone 5 committed**: `infra/local.example.env` documents
`MCP_SERVER_SERIES_DB`, same pattern as `MCP_SERVER_DOCTRINE_PATH`.

### Tool ids and schemas

`series.timelines` (no arguments) -- every known timeline, oldest first,
`is_current_tip`/`cutoff_abs_tick` per `dfseries.timeline.lineage_summary`.

`series.get` (`subject`, `metric` required; `start_abs_tick`, `end_abs_tick`,
`lineage` optional) -- a subject's readings over a window, wrapping
`trend.series`.

`series.latest` (`subject`, `metric` required; `lineage` optional) -- the
most recent reading, wrapping `trend.latest`. `found: false` (no reading in
this lineage) is structurally distinct from `found: true` with
`reading.value: null` (a reading exists, its value is a failed read).

`series.rate` (`subject`, `metric` required; `start_abs_tick`,
`end_abs_tick`, `lineage` optional) -- change per tick, wrapping
`trend.rate`. Refuses to straddle a reset on a `resetting_counter` metric,
exactly as `trend.rate` already refuses.

`series.resets` (`subject`, `metric` required; `start_abs_tick`,
`end_abs_tick`, `lineage` optional) -- reset events and anomalies, wrapping
`trend.resets`.

`series.dwarf_day_events` (`metric` required; `start_abs_tick`,
`end_abs_tick`, `lineage` optional; no `subject` -- it aggregates across
every `unit:*` subject itself) -- wrapping `aggregate.dwarf_day_reset_rate`.

Every schema sets `additionalProperties: false` and every handler
independently rejects an argument outside its own known set (schema
validation is defence in depth, never the real boundary, same rule
`doctrine_tools.py`/`queue_tools.py` already state and this stream
re-verified with `test_unexpected_argument_is_rejected`).

### How each required qualifier appears in the output

Concretely, in `structuredContent` (the XML text form carries the same
information, rendered as attributes -- see `series_tools.py`'s `_xml_num`/
`_xml_str` helpers, which render a `None` numeric value as the literal text
`"null"`, never `"0"`, and never omit the attribute):

- **Rate qualifiers**: `sample_count`, `tick_span`, `skipped_nulls` are
  top-level fields on every `series.rate` result, `dataclasses.asdict`'d
  straight from `trend.RateResult`, never re-keyed or dropped.
- **Metric kind**: `metric_kind` (`"level"` / `"resetting_counter"`) is a
  top-level field on `series.get`, `series.latest`, `series.rate` and
  `series.resets`; `series.dwarf_day_events` carries it too via
  `aggregate.DwarfDayRate`. `series.get`/`series.latest` additionally carry
  `rate_per_tick`, `rate_evidence` and `reset_to_zero_verified` (pulled
  directly from `dfseries.metrics.kind_of`, not re-derived), since a caller
  reading a raw series needs to know *before* trusting any pattern in it
  whether resets even apply here and whether they can be dated exactly.
- **Exact vs interval-bounded**: each `series.resets` event's own `kind`
  field is `"exact_tick"` or `"interval_bounded"`, verbatim from
  `trend.ResetEvent`; an interval-bounded event's `abs_tick` is `None`
  (never a guessed tick).
- **Unavailable, never a number**: `series.rate`'s `status` field is
  `"measured"` or `"unavailable"`; when `"unavailable"`, `value` is always
  `None` and `reason` is always a non-empty string. Verified against both
  the structured dict and the literal XML text (`value="null"` present,
  `value="0"` absent) in `TestRate.test_unavailable_across_a_reset_is_never_a_number`.
- **Superseded, said explicitly**: `series.get` reports an exact
  `superseded_count`, computed from the rows it actually returned (it
  already has them, so this is precise, not a guess). `series.rate`,
  `series.resets` and `series.dwarf_day_events` don't surface raw rows, so
  they instead report `queried_all_timelines` (`lineage == "all"`) -- an
  honest, lineage-level flag rather than a count they cannot cheaply
  produce. `series.latest`'s single `reading` already carries its own
  `superseded` field, so no separate top-level flag was added there.
- **Null is never 0**: no handler in `series_tools.py` ever does
  `value or 0` or a dict `.get(..., 0)` default for a metric value --
  audited by hand while writing the module and proven by
  `TestGet.test_a_null_value_is_never_rendered_as_zero`,
  `TestRate.test_unavailable_across_a_reset_is_never_a_number`, and
  `TestDwarfDayEvents.test_events_per_dwarf_day_is_null_not_zero_when_no_dwarf_days_observed`.
- **Thin aggregates shown prominently**: `series.dwarf_day_events`'s
  `event_count` and `dwarf_days_observed` are the first two attributes in
  the XML text (asserted by string position), and a `caution` field/line
  names the exact counts whenever `event_count` is below 5 (the real
  current figure -- 1 event over 207 dwarf-days -- would trigger it).

### Role grants, with reasons

- **overseer: granted the full six-tool set.** The role that sets
  priority and owns the WIP limit needs grounding in measured trend, not
  just the same live-state screens re-read every cycle -- exactly the
  question this project's own current crisis turns on ("does the well fix
  actually mean the fort is drinking now, or is that still a guess",
  `Working.md`). Granted as one block, matching the breadth of this role's
  other reads (`stocks.*`, `farm.*`, `well.find`, `zone.find`): arbitration
  needs the whole picture, not one metric held back.
- **consultant: granted the full six-tool set.** `docs/TIMESERIES.md`'s
  own design (cited in the handoff) names the consultant as the
  fact-checking role for this data, the live-state analogue of what
  `doctrine.get` already gives it for curated mechanics knowledge:
  role.md's stated limitation ("no retrieval tool... runs on model priors
  alone") is exactly what these six tools answer for live fort history,
  the same way `doctrine.get` already answered it for mechanics.
- **architect: withheld, via a `series.*` wildcard deny with a stated
  reason.** `docs/TIMESERIES.md`'s design explicitly names quartermaster
  (inventory/production trends), the overseer (arbitration) and the
  consultant (fact-checking) as the three roles concerned with this data;
  architect is not one of them, and this role's proposals are spatial
  siting, not a judgment about whether the fort is producing or drinking
  enough. Same shape as the existing `doctrine.get` denial on this role.
- **quartermaster (disabled): granted the full six-tool set anyway.**
  `docs/TIMESERIES.md`'s design names this role the intended owner of
  inventory/production trends. Granting it now, while the role stays
  disabled in `ROSTER.yaml`, means enabling it later is purely a config
  change (`role.md`'s own stated design goal), not a fresh allowlist
  decision -- and `roles.py`'s rule 1 (an allowlist id must exist in the
  registry) is never even evaluated for a disabled role, so this carries
  no load-time risk today.

### `knowledge_scope`: `player_derivable`, with reasons

Set explicitly on every entry in `series_tools.NATIVE_TOOLS` (unlike
`doctrine.get`, which deliberately carries none, because it reads no live
fort/world state at all). Chosen over `player_visible` and `omniscient`
because:

- `dfseries`' subject grammar (`fort`, `unit:<id>`, `item:<TYPE>`,
  `job:<JobType>`) can only ever name the fort's **own** citizens,
  inventory or job queue -- `research/2026-09-16-player-visibility.md`'s
  whole taxonomy turns on fog-of-war gating (`tile_designation.hidden`,
  `dfhack.units.isHidden`, undiscovered map features), none of which this
  subject grammar can ever touch. That rules out `omniscient` outright.
- The closest existing analogs in `scripts/dfhack/TOOLS.yaml` are already
  tagged this way: `stocks.food-drink`/`stocks.seeds` (item stock counts,
  the same shape as `item:<TYPE>` `stock` readings) and
  `labor.unit-status` (per-citizen state, the same shape as `unit:<id>`
  `thirst_timer`/`hunger_timer`/`sleepiness_timer`) are both
  `player_derivable`.
- `player_visible` would overclaim: a vanilla player sees a *qualitative*
  thirst/hunger/sleep signal (a status icon, a bad thought), never the
  literal tick-indexed counter `dfseries` stores or a `rate()`/`resets()`
  computation over it -- a legitimate derived fact, the same distinction
  `connectivity.report` already draws for itself in the same research
  report.

This matters operationally, not just definitionally: `roles.py` rule 7
refuses to load any role holding an `omniscient` tool, for every role
including the sole writer. Getting this wrong as `omniscient` would have
made every `series.*` grant above unloadable; `test_series_tools.py`'s
`TestRosterWiring.test_every_series_tool_is_player_derivable_not_omniscient`
guards against that regressing silently.

### The database path

`series_tools.DEFAULT_SERIES_DB_PATH = "/var/lib/dfseries/uniboslan.series.sqlite3"`,
the exact path `handoffs/2026-09-19-dfseries-auto-import.md` chose,
overridable via `MCP_SERVER_SERIES_DB`
(`dfmcp/server.py`'s `ServerConfig.series_db`). Deliberately a **plain
`str` constant, not a `pathlib.Path`**: this repo's own workstation is
Windows, and `pathlib.Path("/var/lib/...")` constructed there is a
`WindowsPath` whose `str()` renders with backslashes -- wrapping happens
only at the point of use (`series_tools._open`), on whatever string was
actually supplied. A real default is safe here (unlike
`MCP_SERVER_QUEUE_DB`, which has none) because the path is absolute: a
code redeploy resolving a relative path can never land on it by accident,
the specific hazard that forces `queue_db` to stay unset.

**Fails loudly if absent.** `series_tools._open` checks
`Path(series_db_path).is_file()` *before* ever calling
`dfseries.store.connect`, because `store.connect` itself creates an empty,
schema-valid database at any path that does not yet exist -- calling it
first on a missing path would silently serve empty history indistinguishable
from "this fort has recorded nothing." `TestDatabaseAbsent` proves this by
checking the path still does not exist after a refused call, not just that
the call raised.

### What a deploy needs

Nothing on the `dfseries/` side (this stream did not touch it, per its
touched-surfaces boundary) and no new Python dependency (`series_tools.py`
imports only `dfseries` and the standard library, same as `dfseries`
itself). Concretely, for VM 103:

1. Deploy `dfmcp/series_tools.py` and the updated `dfmcp/server.py` and
   `agents/*/tools.yaml` files alongside the rest of `dfmcp/` (the same
   `git -c core.autocrlf=false archive` step other `dfmcp/` deploys already
   use, per `CLAUDE.md`'s deploy trap).
2. Confirm `dfmcp-server.service` runs as the same user that owns
   `/var/lib/dfseries/uniboslan.series.sqlite3` (created `df:df` by
   `dfseries-import.timer` per the auto-import handoff) -- `store.connect`
   opens the file read-write and sets `PRAGMA journal_mode=WAL`, which
   needs write access to the containing directory to create `-wal`/`-shm`
   siblings, even though nothing this module does ever inserts a row. Not
   verified live by this offline stream; flagged for whoever deploys this to
   check (`ls -l /var/lib/dfseries/` and the service's `User=` line in
   `infra/dfmcp-server.service.example`'s deployed copy).
3. Leave `MCP_SERVER_SERIES_DB` unset unless the deploy uses a different
   fort name or install layout than `uniboslan.series.sqlite3` at that
   exact path.
4. Restart `dfmcp-server.service` after deploying: the registry and roster
   are loaded once at process startup (`dfmcp/server.py`'s own docstring,
   "No caching or hot-reload of the registry/roster"), so a code-only
   deploy needs a restart to serve the new tools at all.

No deploy step was actually run by this stream (offline build, no VM, no
SSH, per this handoff's own header) -- the four points above are what the
next stream (or the user) needs to do, not something already done.

### Test counts

`python -m pytest -q` at the repo root: **470 passed, 1 skipped** before
this stream, **529 passed, 1 skipped** after (+59, all in the new
`dfmcp/tests/test_series_tools.py`; five existing fixture files changed to
merge `SERIES_NATIVE_TOOLS` in but gained no new tests of their own).
`dfmcp/tests` alone, ambient (no pinned `mcp` SDK, so `test_server.py`
skips cleanly by design): **162 passed, 1 skipped** before, **221 passed,
1 skipped** after.

## Status: done
