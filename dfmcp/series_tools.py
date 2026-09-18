"""Native ("server-side") MCP tools that read `dfseries`, the fort's own
time-series store (`docs/TIMESERIES.md`): `series.timelines`, `series.get`,
`series.latest`, `series.rate`, `series.resets`, `series.dwarf_day_events`.

The fort records its own history (`dfseries/`) and it imports automatically
on the VM. Until this module, **no agent could see any of it** -- this is
that reader, and only that reader: read-only, no write of any kind, no
insert/update call anywhere in this file.

## Why this is not in `scripts/dfhack/TOOLS.yaml`

Same reasoning as `dfmcp/queue_tools.py` and `dfmcp/doctrine_tools.py`'s own
docstrings, restated because it applies unchanged: none of these six calls
DFHack, runs a Lua script, or touches fort state directly -- they query a
SQLite database (`dfseries/`) that a separate sampler/importer pipeline
already wrote. `registry.py`'s canonical-id scheme and `tools.py`'s
argv-construction heuristic both exist to turn a DFHack CLI signature into a
JSON schema; neither question is meaningful for a tool with no CLI
signature. So, exactly like `queue.*` and `doctrine.get`, these six are
defined here, by hand, as `NativeTool` objects with **explicit,
hand-written JSON schemas**, merged into the same `dfmcp.registry.Registry`
additively via `registry.load_registry`'s `native_tools=` kwarg, and
enforced through the exact same `Roster.check(role, tool_id)` boundary as
every DFHack tool and every other native tool. One boundary, not a second
permission path.

## Wraps `dfseries`, never re-implements it

Every handler below is a thin translation layer over one `dfseries.trend`,
`dfseries.timeline`, `dfseries.aggregate` or `dfseries.metrics` function:
`series.timelines` -> `timeline.lineage_summary`; `series.get` ->
`trend.series`; `series.latest` -> `trend.latest`; `series.rate` ->
`trend.rate`; `series.resets` -> `trend.resets`; `series.dwarf_day_events`
-> `aggregate.dwarf_day_reset_rate`. No reset-detection, rate, or lineage
logic is duplicated here -- this module only opens the database, validates
arguments, calls the one `dfseries` function that already answers the
question, and renders its result two ways (a JSON `structuredContent` and an
XML text block, per `docs/AGENT-ARCHITECTURE.md` §4).

## The property that matters most: every qualifier survives, unflattened

`dfseries` was built specifically to refuse confident nonsense (a rate
straddling a thirst reset used to read "-2.133056/tick" and mean nothing --
`docs/TIMESERIES.md` "Timers reset"). An agent reading a bare number is
exactly how that failure propagated the first time, so every handler here
carries every qualifier `dfseries` produces straight through, never
collapsed into a single figure:

- **Every rate** (`series.rate`) carries `sample_count`, `tick_span` and
  `skipped_nulls` (`trend.RateResult`'s own fields, passed through via
  `dataclasses.asdict`, not re-keyed).
- **Every output that names a metric** (`series.get`, `series.latest`,
  `series.rate`, `series.resets`, `series.dwarf_day_events`) states the
  **metric kind it assumed** (`dfseries.metrics.LEVEL` or
  `.RESETTING_COUNTER`) plus, for a resetting counter, its established
  `rate_per_tick` (or `null` if not established), the `rate_evidence`
  string, and whether **`reset_to_zero_verified`** -- the fact that decides
  whether a reset can be dated to an exact tick at all
  (`dfseries/metrics.py`'s own docstring: "a metric-kind entry with
  `kind=RESETTING_COUNTER` and `rate_per_tick=None` is exactly as valid an
  entry as one with a measured rate").
- **`series.resets`** never blends kinds: each `ResetEvent.kind` is
  `exact_tick` or `interval_bounded`, verbatim from `trend.resets`, and
  `abs_tick` is `null` (never a guessed number) for an interval-bounded
  event.
- **An `unavailable` `series.rate` result is never rendered as a number.**
  `RateResult.value` stays `None` -> JSON `null` -> XML `value="null"`
  (never `"0"`), and `reason` is always present when `status` is
  `unavailable`.
- **A `null` reading is never rendered as `0`, anywhere in this module.**
  No handler below ever does `value or 0` or a dict `.get(..., 0)` default
  for a metric value; a missing/failed reading's `value` field stays
  Python `None` all the way to the wire, and its `error` field (set exactly
  when `value` is `None`, per `docs/TIMESERIES.md`) travels alongside it.
- **A query that reached a superseded timeline says so.** `series.get`
  reports an exact `superseded_count` computed from the rows it actually
  returned (cheap: it already has them). The aggregate-shaped tools
  (`series.rate`, `series.resets`, `series.dwarf_day_events`) do not
  surface raw rows, so they instead report `queried_all_timelines`
  (`lineage == "all"`) -- an honest, lineage-level flag rather than a
  precise count they cannot cheaply produce; `series.latest`'s single
  `reading` already carries its own `superseded` field, so no separate
  top-level flag is added there.
- **`series.dwarf_day_events` shows its event count prominently.** The
  first real drinking-events figure is `event_count=1` over
  `dwarf_days_observed=207.0` -- a number that looks precise and is
  extremely thin. `event_count` and `dwarf_days_observed` are always the
  first two attributes on the XML root, never buried, and the text form
  gets an explicit `<caution>` line whenever `event_count` is below
  `_DWARF_DAY_CAUTION_THRESHOLD` (5), naming the exact counts, so a model
  reading the text block cannot miss that the rate rests on almost nothing.

## `knowledge_scope`: deliberately `player_derivable`, and why (unlike `doctrine.get`)

`doctrine/get`'s own docstring argues, correctly, that `knowledge_scope`
does not apply to it: that tool reads a curated corpus, never fort/world
state. **These six tools are the opposite case**: every metric `dfseries`
stores is a live read of this fort's own state (`docs/TIMESERIES.md`'s
record format), so `knowledge_scope` -- "how a vanilla player could have
come to know this" (`decisions/DECISIONS.md` 2026-09-16) -- is exactly the
right question to ask, and this module answers it rather than leaving the
field unset.

**`player_derivable`**, chosen over `player_visible` or `omniscient`,
because:

- Every `subject` `dfseries` can name is `fort`, `unit:<id>`, `item:<TYPE>`
  or `job:<JobType>` (`docs/TIMESERIES.md`'s closed subject grammar) --
  always the fort's **own** citizens, own inventory, or own job queue.
  `research/2026-09-16-player-visibility.md`'s whole taxonomy turns on
  fog-of-war gating (`tile_designation.hidden`, `dfhack.units.isHidden`,
  undiscovered map features): none of that applies here, because nothing
  in this module's subject grammar can ever name an unrevealed tile, a
  sneaking/off-map unit, or an undiscovered vein. That rules out
  `omniscient` outright -- this is structurally the same shape as
  `labor.unit-status` ("always the player's own"), which the same report
  tags `player_derivable`, and as `stuckjobs.find` (`world.jobs.list`,
  tagged `player_visible`, "every entry exists only because the player's
  own dwarves created it").
- The closest existing registry analogs for the actual metric families
  `dfseries` carries are already tagged, in `scripts/dfhack/TOOLS.yaml`:
  `stocks.food-drink`/`stocks.seeds` (item stock counts, the closest analog
  to `item:<TYPE>` `stock` readings) are `player_derivable`;
  `labor.unit-status` (per-citizen state, the closest analog to
  `unit:<id>` `thirst_timer`/`hunger_timer`/`sleepiness_timer`) is also
  `player_derivable`. This module's own subject/metric shape does not
  introduce anything those two tags do not already cover.
- `player_visible` would overclaim: a vanilla player sees a *qualitative*
  signal for thirst/hunger/sleep (a status icon, a bad thought, a dwarf
  visibly walking to a water source) but never the literal `thirst_timer`
  tick count `dfseries` stores, and never a `resets()`/`rate()` computation
  over a tick-indexed history -- both are legitimate derived facts, not raw
  screens, the same distinction `connectivity.report` already draws for
  itself in the same report ("a vanilla player has no literal 'connectivity
  report' screen -- this is a legitimate derived fact").

Unlike `doctrine.get`, this module's `NativeTool` **does** set
`knowledge_scope` explicitly (`"player_derivable"`, a class attribute on
every entry in `NATIVE_TOOLS` below) so `dfmcp.roles` rule 7 evaluates it
like any DFHack tool's tag, rather than treating it as "not this rule's
concern" the way a tool with no fort/world reads at all (`queue.*`,
`doctrine.get`) correctly is.

## The database path: absolute, so a default here is safe (unlike `queue_db`)

`dfmcp/server.py`'s `ServerConfig.queue_db` has **no default**, because its
in-tree default (`dfqueue/<fort>.sqlite3`) sits *inside* the code checkout,
so a code redeploy could resolve a relative path onto live data and clobber
it. `dfseries`'s own deploy chose an **absolute**, out-of-tree path,
`/var/lib/dfseries/uniboslan.series.sqlite3`
(`handoffs/2026-09-19-dfseries-auto-import.md`, "Database path, chosen
deliberately") -- a code redeploy resolving relative to wherever the
checkout happens to be can never land on an absolute path by accident, so
the concern that forces `queue_db` to have no default does not apply here.
`DEFAULT_SERIES_DB_PATH` below is that path, safe as a real default,
overridable via `MCP_SERVER_SERIES_DB` for a deploy layout that differs
(mirroring `MCP_SERVER_QUEUE_DB`'s naming, since both name a runtime SQLite
file outside the tree -- not `MCP_SERVER_DOCTRINE_PATH`'s naming, which
names an in-tree YAML file, a different case).

**Deliberately a plain `str` constant, not a `pathlib.Path`.** This repo's
own workstation is Windows (`CLAUDE.md`); `pathlib.Path("/var/lib/...")`
constructed on Windows is a `WindowsPath` whose `str()` renders with
backslashes, which would silently misrepresent a Linux deploy path in this
module's own source. Wrapping happens once, at the point of use
(`_require_db` below), via `pathlib.Path(series_db_path)` on whatever string
was actually supplied -- never baked into the module-level constant.

**Fails loudly if the database is absent** (`_require_db`): `_require_db`
checks `Path(series_db_path).is_file()` *before* ever calling
`dfseries.store.connect`, because `store.connect` itself creates an empty,
schema-valid database at any path that does not yet exist (`p.parent.mkdir
(parents=True, exist_ok=True)` then `sqlite3.connect(p)`,
`dfseries/store.py`) -- calling it first on a missing path would silently
serve empty history that reads exactly like "this fort has recorded
nothing" instead of "the store is missing." Same failure mode
`doctrine_tools.py`'s `_load_entries` refuses for the same reason.

## Where files live at runtime, and why re-opened per call

`series_db_path` is a parameter to `call()`, exactly mirroring how
`dfmcp/queue_tools.py`'s `db_path` and `dfmcp/doctrine_tools.py`'s
`doctrine_path` are threaded through from `dfmcp/server.py`'s
`ServerConfig`, never a module-level constant baked at import time. The
connection is opened and closed within each `call()` (via `dfseries.
store.connect`'s own context manager), not held across calls: this
project's sample volume is small (one event per game day, per
`docs/TIMESERIES.md`), so a fresh connection per call costs nothing and
means a server never holds a long-lived handle on a file an external
importer keeps appending to.

`async def` throughout, matching `queue_tools.call`/`doctrine_tools.call`'s
shape so `dfmcp/server.py`'s dispatch can `await` any native module
uniformly, even though nothing here actually awaits: the underlying reads
are plain, fast `sqlite3` calls, not pushed to a thread, for the same
reason `doctrine_tools.py` gives for its own synchronous file read.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Tuple
from xml.sax.saxutils import quoteattr

from dfseries import aggregate, schema as series_schema, store, timeline, trend
from dfseries import metrics as metric_kinds

# --------------------------------------------------------------------------
# Tool ids
# --------------------------------------------------------------------------

SERIES_TIMELINES = "series.timelines"
SERIES_GET = "series.get"
SERIES_LATEST = "series.latest"
SERIES_RATE = "series.rate"
SERIES_RESETS = "series.resets"
SERIES_DWARF_DAY_EVENTS = "series.dwarf_day_events"

NATIVE_TOOL_IDS = (
    SERIES_TIMELINES, SERIES_GET, SERIES_LATEST, SERIES_RATE, SERIES_RESETS, SERIES_DWARF_DAY_EVENTS,
)

# See module docstring, "The database path": a plain str, never a Path,
# because this is a foreign-platform (Linux VM) absolute path and this
# repo's workstation is Windows.
DEFAULT_SERIES_DB_PATH = "/var/lib/dfseries/uniboslan.series.sqlite3"

_LINEAGE_VALUES = ("current", "all")

_DWARF_DAY_CAUTION_THRESHOLD = 5


class SeriesToolError(Exception):
    """A `series.*` call is refused: bad arguments, an unrecognised
    lineage, or the `dfseries` database being absent/unreadable/schema-
    mismatched. Always caught by `dfmcp.server` and turned into an MCP tool
    result with `isError=True` carrying this exception's message -- never
    raised past that boundary, matching `queue_tools.QueueToolError` and
    `doctrine_tools.DoctrineToolError`."""


# --------------------------------------------------------------------------
# NativeTool: what registry.py and roles.py need, duck-typed against Tool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeTool:
    """See this module's docstring for exactly why `knowledge_scope` is set
    here (unlike `doctrine_tools.NativeTool`, which deliberately omits it)
    and why every entry shares the same value: all six tools read the same
    class of thing (this fort's own recorded state, never a hidden tile,
    unit or feature)."""

    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()
    knowledge_scope: str = "player_derivable"

    def describe(self, role: str) -> Tuple[str, dict]:
        # `role` accepted (dfmcp.tools.tool_definitions always passes it)
        # but unused: none of these six schemas vary by caller, matching
        # doctrine.get's own describe().
        del role
        try:
            return _DESCRIPTIONS[self.id]
        except KeyError:  # pragma: no cover -- every id in NATIVE_TOOLS has an entry below
            raise AssertionError(f"NativeTool.describe: unknown id {self.id!r}")


NATIVE_TOOLS: Dict[str, NativeTool] = {tid: NativeTool(id=tid) for tid in NATIVE_TOOL_IDS}


# --------------------------------------------------------------------------
# Schemas and descriptions: hand-written, per this module's docstring
# --------------------------------------------------------------------------

_SUBJECT_PROP = {
    "type": "string",
    "description": (
        "The subject to query: 'fort' for a fort-wide metric, 'unit:<id>' for one "
        "citizen, 'item:<TYPE>' for one fort-owned item type's stock, or "
        "'job:<JobType>' for one job type's queue depth (docs/TIMESERIES.md's "
        "subject grammar; never a coordinate). No enum enforced: the store "
        "accepts subjects the sampler has not recorded yet, and an empty result "
        "for an unrecognised subject is the honest answer, not a refusal."
    ),
}

_METRIC_PROP = {
    "type": "string",
    "description": (
        "The metric name, e.g. 'thirst_timer', 'hunger_timer', 'sleepiness_timer', "
        "'population', 'deaths', 'stock', 'queue_depth' (docs/TIMESERIES.md's "
        "starter metric set) or any metric the sampler has added since. No enum "
        "enforced: an unrecognised metric is accepted and treated as an ordinary "
        "level reading (dfseries/metrics.py's 'unknown metrics default to level')."
    ),
}

_START_TICK_PROP = {
    "type": "integer",
    "description": "Inclusive lower bound on abs_tick (the fort's absolute game tick, never a bare tick that resets yearly). Omit for no lower bound.",
}

_END_TICK_PROP = {
    "type": "integer",
    "description": "Inclusive upper bound on abs_tick. Omit for no upper bound.",
}

_LINEAGE_PROP = {
    "type": "string",
    "enum": list(_LINEAGE_VALUES),
    "default": "current",
    "description": (
        "'current' (default): only the surviving lineage after any rollback -- "
        "a rate or reset computed across a rollback boundary never happens by "
        "default. 'all': every timeline including superseded branches "
        "(docs/TIMESERIES.md 'Timelines'); a superseded branch is a real "
        "observation of a future that did not happen, kept because it may "
        "still be worth something, but asking across it must be an explicit "
        "choice, never the default."
    ),
}

_GET_DESCRIPTION = (
    "One subject's readings of one metric over a tick window, oldest first, "
    "wrapping dfseries.trend.series(). Every reading carries its abs_tick, "
    "value (a number or null -- null is never rendered as 0, and always "
    "carries a non-empty error string explaining the failed read), unit, "
    "error, timeline_id and superseded flag, unflattened. The response also "
    "states the metric's kind (level or resetting_counter), its established "
    "rate_per_tick and evidence if it resets, and an exact superseded_count "
    "computed from the rows actually returned -- call series.timelines first "
    "if you need to know which timeline is the current tip."
)
_GET_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "metric"],
    "properties": {
        "subject": _SUBJECT_PROP,
        "metric": _METRIC_PROP,
        "start_abs_tick": _START_TICK_PROP,
        "end_abs_tick": _END_TICK_PROP,
        "lineage": _LINEAGE_PROP,
    },
}
_GET_FIELDS = {"subject", "metric", "start_abs_tick", "end_abs_tick", "lineage"}

_LATEST_DESCRIPTION = (
    "The single most recent reading (by abs_tick) of one metric for one "
    "subject, wrapping dfseries.trend.latest(). 'found' is false (with "
    "reading: null) when this subject/metric has no reading at all in this "
    "lineage -- distinct from 'found' true with reading.value: null, which "
    "means the most recent sample exists but was itself a failed read "
    "(reading.error explains why). States the metric's kind, established "
    "rate_per_tick/evidence and reset_to_zero_verified the same way "
    "series.get does."
)
_LATEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "metric"],
    "properties": {
        "subject": _SUBJECT_PROP,
        "metric": _METRIC_PROP,
        "lineage": _LINEAGE_PROP,
    },
}
_LATEST_FIELDS = {"subject", "metric", "lineage"}

_RATE_DESCRIPTION = (
    "Change per tick over a window, wrapping dfseries.trend.rate(). Every "
    "result states status (measured/unavailable -- an unavailable result "
    "carries a reason and value is always null, never a number), "
    "sample_count, tick_span and skipped_nulls, and the metric_kind it "
    "assumed. For a resetting_counter metric this refuses to let the slope "
    "straddle a reset (docs/TIMESERIES.md 'Timers reset: a rate across a "
    "reset is meaningless'): segment is 'endpoint' when no reset fell in the "
    "window, 'between_reset' when the slope was recomputed from after the "
    "last one (used_start_abs_tick names where from), or the result is "
    "unavailable if too few readings remain after the reset. Call "
    "series.resets first to see the reset(s) responsible for a "
    "between_reset or unavailable result."
)
_RATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "metric"],
    "properties": {
        "subject": _SUBJECT_PROP,
        "metric": _METRIC_PROP,
        "start_abs_tick": _START_TICK_PROP,
        "end_abs_tick": _END_TICK_PROP,
        "lineage": _LINEAGE_PROP,
    },
}
_RATE_FIELDS = {"subject", "metric", "start_abs_tick", "end_abs_tick", "lineage"}

_RESETS_DESCRIPTION = (
    "Reset events for one subject's resetting-counter metric over a window, "
    "wrapping dfseries.trend.resets() (docs/TIMESERIES.md 'Timers reset'). "
    "Each event's kind is exact_tick (abs_tick names the tick the reset "
    "happened, only possible when the metric's rate is established AND "
    "reset_to_zero_verified) or interval_bounded (abs_tick is null -- only "
    "'somewhere in (window_start_abs_tick, window_end_abs_tick]' can be "
    "said). Anomalies (a rise impossible for the established rate) are "
    "reported separately, never folded into events. A level metric always "
    "returns empty events/anomalies: resets are not a concept that applies "
    "to it, which the response's own metric_kind field makes visible rather "
    "than silent."
)
_RESETS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "metric"],
    "properties": {
        "subject": _SUBJECT_PROP,
        "metric": _METRIC_PROP,
        "start_abs_tick": _START_TICK_PROP,
        "end_abs_tick": _END_TICK_PROP,
        "lineage": _LINEAGE_PROP,
    },
}
_RESETS_FIELDS = {"subject", "metric", "start_abs_tick", "end_abs_tick", "lineage"}

_DWARF_DAY_DESCRIPTION = (
    "Reset events for one metric aggregated across every unit:* subject in "
    "a window, divided by citizen-days observed, wrapping "
    "dfseries.aggregate.dwarf_day_reset_rate(). For thirst_timer this is "
    "drinking events per dwarf-day. event_count and dwarf_days_observed are "
    "always reported prominently (first, before the derived rate), because "
    "the real current figure is extremely thin (1 event over 207 "
    "dwarf-days) and a caller must see the sample size before trusting "
    "events_per_dwarf_day, which is null (never a division by zero) when no "
    "dwarf-days were observed. exact_tick_events and interval_bounded_events "
    "are split out, never blended into one total without the split alongside."
)
_DWARF_DAY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["metric"],
    "properties": {
        "metric": _METRIC_PROP,
        "start_abs_tick": _START_TICK_PROP,
        "end_abs_tick": _END_TICK_PROP,
        "lineage": _LINEAGE_PROP,
    },
}
_DWARF_DAY_FIELDS = {"metric", "start_abs_tick", "end_abs_tick", "lineage"}

_TIMELINES_DESCRIPTION = (
    "Every known timeline (one continuous run of the game from one map "
    "load, docs/TIMESERIES.md 'Timelines'), oldest first, wrapping "
    "dfseries.timeline.lineage_summary(). is_current_tip marks the one "
    "timeline nothing supersedes; every other timeline's cutoff_abs_tick "
    "names the tick at which its own immediate successor began -- samples "
    "after that tick belong to a discarded branch. Takes no arguments."
)
_TIMELINES_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {}}
_TIMELINES_FIELDS: set = set()

_DESCRIPTIONS: Dict[str, Tuple[str, dict]] = {
    SERIES_TIMELINES: (_TIMELINES_DESCRIPTION, _TIMELINES_SCHEMA),
    SERIES_GET: (_GET_DESCRIPTION, _GET_SCHEMA),
    SERIES_LATEST: (_LATEST_DESCRIPTION, _LATEST_SCHEMA),
    SERIES_RATE: (_RATE_DESCRIPTION, _RATE_SCHEMA),
    SERIES_RESETS: (_RESETS_DESCRIPTION, _RESETS_SCHEMA),
    SERIES_DWARF_DAY_EVENTS: (_DWARF_DAY_DESCRIPTION, _DWARF_DAY_SCHEMA),
}


# --------------------------------------------------------------------------
# Argument validation -- real enforcement, not just the schema's
# additionalProperties: false. Same pattern doctrine_tools._reject_unknown_
# arguments and queue_tools's function of the same name already use: a
# client need not validate against the schema it was handed.
# --------------------------------------------------------------------------


def _reject_unknown_arguments(tool_id: str, arguments: Mapping[str, Any], known: set) -> None:
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise SeriesToolError(
            f"{tool_id}: unexpected argument(s) {unknown}; accepts only {sorted(known)}"
        )


def _require_str(tool_id: str, arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise SeriesToolError(f"{tool_id}: '{name}' must be a non-empty string, got {value!r}")
    return value


def _optional_int(tool_id: str, arguments: Mapping[str, Any], name: str) -> Optional[int]:
    value = arguments.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SeriesToolError(f"{tool_id}: '{name}' must be an integer, got {value!r}")
    return value


def _lineage(tool_id: str, arguments: Mapping[str, Any]) -> str:
    value = arguments.get("lineage", "current")
    if value not in _LINEAGE_VALUES:
        raise SeriesToolError(
            f"{tool_id}: 'lineage' must be one of {list(_LINEAGE_VALUES)}, got {value!r}"
        )
    return value


# --------------------------------------------------------------------------
# Opening the database -- see module docstring, "Fails loudly if the
# database is absent"
# --------------------------------------------------------------------------


@contextmanager
def _open(series_db_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(series_db_path)
    if not path.is_file():
        raise SeriesToolError(
            f"dfseries database not found at {path} -- set MCP_SERVER_SERIES_DB "
            "(or pass series_db_path explicitly) to the real location, or wait "
            "for the sampler/importer to create it. Refusing to open (which "
            "would silently create an empty, schema-valid database at this "
            "path) rather than serving empty history that reads as 'this fort "
            "has recorded nothing' instead of 'the store is missing'."
        )
    try:
        with store.connect(path) as conn:
            yield conn
    except series_schema.SchemaError as exc:
        raise SeriesToolError(f"dfseries database at {path}: {exc}") from exc


# --------------------------------------------------------------------------
# Rendering helpers -- see module docstring: a null value is never rendered
# as 0, anywhere below.
# --------------------------------------------------------------------------


def _xml_num(value: Any) -> str:
    """A numeric (or None) value for an XML attribute. None -> the literal
    text 'null', never '0' and never an omitted attribute -- omitting it
    would let a reader assume the field just wasn't relevant here, rather
    than seeing that a real reading was missing."""
    return "null" if value is None else str(value)


def _xml_str(value: Any) -> str:
    """An optional string (unit, error, reason, evidence, timeline_id) for
    an XML attribute. None -> an empty quoted string: these are fields
    where 'absent' is the natural reading (no unit recorded, no error, no
    reason given), unlike a numeric value where None is itself the
    information."""
    return quoteattr("" if value is None else str(value))


def _reading_xml(reading: Optional[dict]) -> str:
    if reading is None:
        return "  <reading/>"
    return (
        f'  <reading abs_tick="{_xml_num(reading["abs_tick"])}" '
        f'value="{_xml_num(reading["value"])}" unit={_xml_str(reading["unit"])} '
        f'error={_xml_str(reading["error"])} timeline_id={_xml_str(reading["timeline_id"])} '
        f'superseded="{str(bool(reading["superseded"])).lower()}"/>'
    )


def _kind_attrs(mk: "metric_kinds.MetricKind") -> str:
    return (
        f'metric_kind="{mk.kind}" rate_per_tick="{_xml_num(mk.rate_per_tick)}" '
        f'reset_to_zero_verified="{str(mk.reset_to_zero_verified).lower()}" '
        f'rate_evidence={_xml_str(mk.evidence)}'
    )


# --------------------------------------------------------------------------
# Handlers -- each wraps exactly one dfseries function
# --------------------------------------------------------------------------


async def _timelines(role: str, arguments: Mapping[str, Any], *, conn: sqlite3.Connection) -> Tuple[str, dict]:
    del role
    _reject_unknown_arguments(SERIES_TIMELINES, arguments, _TIMELINES_FIELDS)
    rows = timeline.lineage_summary(conn)

    lines = [f'<timelines count="{len(rows)}">']
    for r in rows:
        lines.append(
            f'  <timeline id={_xml_str(r["timeline_id"])} start_abs_tick="{_xml_num(r["start_abs_tick"])}" '
            f'first_wall_utc={_xml_str(r["first_wall_utc"])} cutoff_abs_tick="{_xml_num(r["cutoff_abs_tick"])}" '
            f'is_current_tip="{str(bool(r["is_current_tip"])).lower()}"/>'
        )
    lines.append("</timelines>")

    return "\n".join(lines), {"count": len(rows), "timelines": rows}


async def _get(role: str, arguments: Mapping[str, Any], *, conn: sqlite3.Connection) -> Tuple[str, dict]:
    del role
    _reject_unknown_arguments(SERIES_GET, arguments, _GET_FIELDS)
    subject = _require_str(SERIES_GET, arguments, "subject")
    metric = _require_str(SERIES_GET, arguments, "metric")
    start = _optional_int(SERIES_GET, arguments, "start_abs_tick")
    end = _optional_int(SERIES_GET, arguments, "end_abs_tick")
    lineage_value = _lineage(SERIES_GET, arguments)

    rows = trend.series(conn, subject, metric, start_abs_tick=start, end_abs_tick=end, lineage=lineage_value)
    mk = metric_kinds.kind_of(metric)
    superseded_count = sum(1 for r in rows if r["superseded"])

    lines = [
        f'<series subject={_xml_str(subject)} metric={_xml_str(metric)} lineage="{lineage_value}" '
        f'{_kind_attrs(mk)} count="{len(rows)}" superseded_count="{superseded_count}">'
    ]
    for r in rows:
        lines.append(_reading_xml(r))
    lines.append("</series>")

    structured = {
        "subject": subject, "metric": metric, "lineage": lineage_value,
        "metric_kind": mk.kind, "rate_per_tick": mk.rate_per_tick,
        "reset_to_zero_verified": mk.reset_to_zero_verified, "rate_evidence": mk.evidence,
        "count": len(rows), "superseded_count": superseded_count, "readings": rows,
    }
    return "\n".join(lines), structured


async def _latest(role: str, arguments: Mapping[str, Any], *, conn: sqlite3.Connection) -> Tuple[str, dict]:
    del role
    _reject_unknown_arguments(SERIES_LATEST, arguments, _LATEST_FIELDS)
    subject = _require_str(SERIES_LATEST, arguments, "subject")
    metric = _require_str(SERIES_LATEST, arguments, "metric")
    lineage_value = _lineage(SERIES_LATEST, arguments)

    reading = trend.latest(conn, subject, metric, lineage=lineage_value)
    mk = metric_kinds.kind_of(metric)

    lines = [
        f'<latest subject={_xml_str(subject)} metric={_xml_str(metric)} lineage="{lineage_value}" '
        f'{_kind_attrs(mk)} found="{str(reading is not None).lower()}">',
        _reading_xml(reading),
        "</latest>",
    ]

    structured = {
        "subject": subject, "metric": metric, "lineage": lineage_value,
        "metric_kind": mk.kind, "rate_per_tick": mk.rate_per_tick,
        "reset_to_zero_verified": mk.reset_to_zero_verified, "rate_evidence": mk.evidence,
        "found": reading is not None, "reading": reading,
    }
    return "\n".join(lines), structured


async def _rate(role: str, arguments: Mapping[str, Any], *, conn: sqlite3.Connection) -> Tuple[str, dict]:
    del role
    _reject_unknown_arguments(SERIES_RATE, arguments, _RATE_FIELDS)
    subject = _require_str(SERIES_RATE, arguments, "subject")
    metric = _require_str(SERIES_RATE, arguments, "metric")
    start = _optional_int(SERIES_RATE, arguments, "start_abs_tick")
    end = _optional_int(SERIES_RATE, arguments, "end_abs_tick")
    lineage_value = _lineage(SERIES_RATE, arguments)

    result = trend.rate(conn, subject, metric, start_abs_tick=start, end_abs_tick=end, lineage=lineage_value)
    fields = dataclasses.asdict(result)

    lines = [
        f'<rate subject={_xml_str(subject)} metric={_xml_str(metric)} lineage="{lineage_value}" '
        f'queried_all_timelines="{str(lineage_value == "all").lower()}" status="{result.status}" '
        f'value="{_xml_num(result.value)}" sample_count="{result.sample_count}" '
        f'tick_span="{_xml_num(result.tick_span)}" skipped_nulls="{result.skipped_nulls}" '
        f'metric_kind="{result.metric_kind}" segment={_xml_str(result.segment)} '
        f'used_start_abs_tick="{_xml_num(result.used_start_abs_tick)}" reason={_xml_str(result.reason)}/>'
    ]

    structured = {
        "subject": subject, "metric": metric, "lineage": lineage_value,
        "queried_all_timelines": lineage_value == "all", **fields,
    }
    return "\n".join(lines), structured


def _event_xml(event) -> str:
    return (
        f'  <event kind="{event.kind}" abs_tick="{_xml_num(event.abs_tick)}" '
        f'window_start_abs_tick="{_xml_num(event.window_start_abs_tick)}" '
        f'window_end_abs_tick="{_xml_num(event.window_end_abs_tick)}" '
        f'from_value="{_xml_num(event.from_value)}" to_value="{_xml_num(event.to_value)}"/>'
    )


def _anomaly_xml(anomaly) -> str:
    return (
        f'  <anomaly window_start_abs_tick="{_xml_num(anomaly.window_start_abs_tick)}" '
        f'window_end_abs_tick="{_xml_num(anomaly.window_end_abs_tick)}" '
        f'from_value="{_xml_num(anomaly.from_value)}" to_value="{_xml_num(anomaly.to_value)}" '
        f'reason={_xml_str(anomaly.reason)}/>'
    )


async def _resets(role: str, arguments: Mapping[str, Any], *, conn: sqlite3.Connection) -> Tuple[str, dict]:
    del role
    _reject_unknown_arguments(SERIES_RESETS, arguments, _RESETS_FIELDS)
    subject = _require_str(SERIES_RESETS, arguments, "subject")
    metric = _require_str(SERIES_RESETS, arguments, "metric")
    start = _optional_int(SERIES_RESETS, arguments, "start_abs_tick")
    end = _optional_int(SERIES_RESETS, arguments, "end_abs_tick")
    lineage_value = _lineage(SERIES_RESETS, arguments)

    result = trend.resets(conn, subject, metric, start_abs_tick=start, end_abs_tick=end, lineage=lineage_value)
    mk = metric_kinds.kind_of(metric)

    lines = [
        f'<resets subject={_xml_str(subject)} metric={_xml_str(metric)} lineage="{lineage_value}" '
        f'queried_all_timelines="{str(lineage_value == "all").lower()}" {_kind_attrs(mk)} '
        f'event_count="{len(result.events)}" anomaly_count="{len(result.anomalies)}">'
    ]
    for e in result.events:
        lines.append(_event_xml(e))
    for a in result.anomalies:
        lines.append(_anomaly_xml(a))
    lines.append("</resets>")

    structured = {
        "subject": subject, "metric": metric, "lineage": lineage_value,
        "queried_all_timelines": lineage_value == "all",
        "metric_kind": result.metric_kind, "rate_per_tick": result.rate_per_tick,
        "rate_evidence": result.rate_evidence, "reset_to_zero_verified": mk.reset_to_zero_verified,
        "events": [dataclasses.asdict(e) for e in result.events],
        "anomalies": [dataclasses.asdict(a) for a in result.anomalies],
    }
    return "\n".join(lines), structured


async def _dwarf_day_events(role: str, arguments: Mapping[str, Any], *, conn: sqlite3.Connection) -> Tuple[str, dict]:
    del role
    _reject_unknown_arguments(SERIES_DWARF_DAY_EVENTS, arguments, _DWARF_DAY_FIELDS)
    metric = _require_str(SERIES_DWARF_DAY_EVENTS, arguments, "metric")
    start = _optional_int(SERIES_DWARF_DAY_EVENTS, arguments, "start_abs_tick")
    end = _optional_int(SERIES_DWARF_DAY_EVENTS, arguments, "end_abs_tick")
    lineage_value = _lineage(SERIES_DWARF_DAY_EVENTS, arguments)

    result = aggregate.dwarf_day_reset_rate(
        conn, metric, start_abs_tick=start, end_abs_tick=end, lineage=lineage_value,
    )
    fields = dataclasses.asdict(result)

    if result.dwarf_days_observed > 0:
        rate_status, rate_reason = "measured", None
    else:
        rate_status = "unavailable"
        rate_reason = (
            f"no dwarf-days observed for metric {metric!r} in this window -- at least one "
            "unit:* subject needs two readings at distinct abs_tick"
        )

    caution = None
    if result.event_count < _DWARF_DAY_CAUTION_THRESHOLD:
        caution = (
            f"resting on only {result.event_count} event(s) over "
            f"{result.dwarf_days_observed} dwarf-day(s) observed across "
            f"{result.subjects_observed} subject(s) -- do not generalise "
            "events_per_dwarf_day from a sample this small."
        )

    lines = [
        f'<dwarf_day_events metric={_xml_str(metric)} event_count="{result.event_count}" '
        f'dwarf_days_observed="{result.dwarf_days_observed}" lineage="{lineage_value}" '
        f'queried_all_timelines="{str(lineage_value == "all").lower()}" label={_xml_str(result.label)} '
        f'metric_kind="{result.metric_kind}" rate_per_tick="{_xml_num(result.rate_per_tick)}" '
        f'exact_tick_events="{result.exact_tick_events}" interval_bounded_events="{result.interval_bounded_events}" '
        f'anomaly_count="{result.anomaly_count}" subjects_observed="{result.subjects_observed}" '
        f'events_per_dwarf_day="{_xml_num(result.events_per_dwarf_day)}" '
        f'events_per_dwarf_day_status="{rate_status}" events_per_dwarf_day_reason={_xml_str(rate_reason)}>'
    ]
    if caution:
        lines.append(f"  <caution>{caution}</caution>")
    lines.append("</dwarf_day_events>")

    structured = {
        "lineage": lineage_value, "queried_all_timelines": lineage_value == "all",
        "events_per_dwarf_day_status": rate_status, "events_per_dwarf_day_reason": rate_reason,
        "caution": caution, **fields,
    }
    return "\n".join(lines), structured


_HANDLERS = {
    SERIES_TIMELINES: _timelines,
    SERIES_GET: _get,
    SERIES_LATEST: _latest,
    SERIES_RATE: _rate,
    SERIES_RESETS: _resets,
    SERIES_DWARF_DAY_EVENTS: _dwarf_day_events,
}


async def call(
    tool_id: str, role: str, arguments: Mapping[str, Any], *,
    series_db_path: str | Path = DEFAULT_SERIES_DB_PATH,
) -> Tuple[str, Optional[dict]]:
    """Dispatch one native tool call. Returns `(text, structured)` for
    `dfmcp.server` to wrap into a `CallToolResult(isError=False, ...)`, or
    raises `SeriesToolError` for `dfmcp.server` to turn into `isError=True`.
    Never called for an id outside `NATIVE_TOOL_IDS` -- `dfmcp.server` only
    reaches this after confirming `registry.get(tool_id)` is a native tool
    belonging to this module."""
    handler = _HANDLERS.get(tool_id)
    if handler is None:  # pragma: no cover -- server.py only routes known native ids here
        raise AssertionError(f"series_tools.call: unknown native tool id {tool_id!r}")
    with _open(series_db_path) as conn:
        return await handler(role, arguments, conn=conn)
