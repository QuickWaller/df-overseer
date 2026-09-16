"""Live, mid-fort signals: mechanical facts read straight off an existing
DFHack read tool, never a coordinate.

`learning/predictions/` can only grade against the **fort ledger**
(`learning/ledger/`), which is one row per fort written mostly at embark and
at the end (see that module's own README, "The scope this is deliberately
built at"). `dfqueue/`'s proposals need something else: a **mid-fort**
prediction like "the new workshop ends up within 7 tiles of the Wagon" or
"stuck jobs drop to zero", checked a few hundred ticks later against the same
running fort. Neither the ledger nor `learning/predictions/` can express
that, and this module does not touch either of them — it is a second, small,
closed registry that reads live tool output instead of a ledger row.

A **live signal** is a dotted name built only from fixed words and
(double-quoted) landmark names — never a raw coordinate, per
`docs/PURPOSE.md` design commitment #1. This module owns exactly two
operations:

- `parse(signal)` — is this string syntactically one of the known live
  signals? Returns a `ParsedSignal` or raises `SignalError`. Purely
  syntactic: it does not touch DFHack, a live fort, or even check that a
  named landmark currently exists.
- `read(parsed, call_tool)` — given `parsed` and an **injected**
  `call_tool(tool_id, arguments) -> parsed_json` function, produce this
  cycle's actual value, or `UNRESOLVABLE` for a landmark/exit that doesn't
  exist (yet). No DFHack or MCP import appears anywhere in this file: the
  caller (`dfqueue.grade`, or a test) supplies `call_tool`, so this module
  has no runtime dependency on a live game, `dfmcp/`, or a socket.

## Why "unresolvable" is not the same as "invalid"

A proposal is allowed to predict about something it is itself proposing to
build — run #1's real proposal (`evals/live/2026-09-14-architect-first-charter/
run.json`) predicts a distance from a workshop that does not exist yet at
write time. `parse()` accepts that signal (the *name* is well-formed); only
`read()`, later, at grading time, can discover the landmark still doesn't
exist, and reports that as `UNRESOLVABLE`, never as a parse failure and
never as a grading error.

## The initial signal set

| signal | tool | value |
|---|---|---|
| `fort.population` | `overview.get` | `tier1.population` (int) |
| `fort.alerts.count` | `overview.get` | `len(tier2.alerts)` |
| `fort.stuck_jobs.count` | `stuckjobs.find` | `len(result)` (a bare array) |
| `fort.landmarks.count` | `landmarks.list` | `len(result)` (a bare array) |
| `landmark."A".exists` | `landmarks.list` | whether a landmark named A is in the list |
| `landmark."A".exit."B".distance_tiles` | `landmarks.get A` | the `distance_tiles` of the exit whose `to` is B |

Tool ids and shapes are `scripts/dfhack/TOOLS.yaml` / `scripts/dfhack/
df-overseer-overview.lua` / `df-overseer-landmarks.lua` /
`df-overseer-stuckjobs.lua`, read directly for this module rather than
assumed — `overview.get` nests `population` under `tier1` and `alerts`
under `tier2`; `stuckjobs.find` and `landmarks.list` both print a **bare
JSON array**, not an object with a `result` key.

## The `stocks.*` signals — added `handoffs/2026-09-16-stocks-read-and-labor-race.md`

Added to close the exact gap that stream's own brief names: without these,
a proposal cannot predict "fort-owned drink rises above zero", because
nothing in this closed registry read the fort's actual (not caravan-owned)
stores. Backed by the new `scripts/dfhack/df-overseer-stocks.lua`, whose own
header comment carries the live-verified reason its ownership test is
`not item.flags.trader`, never `not item.flags.foreign` — `foreign` is an
origin flag, true on the fort's OWN unclaimed embark supplies too, not a
fort-vs-caravan ownership test.

| signal | tool | value |
|---|---|---|
| `stocks.drink.count` | `stocks.food-drink` | `drink.count` (int) |
| `stocks.prepared_meals.count` | `stocks.food-drink` | `prepared_meals.count` (int) |
| `stocks.raw_edibles.count` | `stocks.food-drink` | `raw_edibles.count` (int) |
| `stocks.seeds.count` | `stocks.seeds` | `total` (int) |

Each of these is a fixed signal name, exactly like `fort.population` — none
of them take a landmark argument, since a stock count has no spatial
component at all.

## Quoting a landmark name

Landmark names come straight from the game (`"Stockpile #2"`) and may
contain spaces and `#`; neither needs escaping inside the quotes that wrap
a name in a signal string. The one character that does need escaping is a
literal double quote, as `\\"` (and a literal backslash as `\\\\`), so the
parser can find the closing quote unambiguously. `quote_landmark_name()`
below is the one place that escaping happens, so a caller building a signal
string never has to hand-escape one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .ledger.schema import MECHANICAL

SCHEMA_VERSION = 1

# ---- value types --------------------------------------------------------------

INTEGER, BOOLEAN = "integer", "boolean"

# ---- signal kinds ---------------------------------------------------------------

FORT_POPULATION = "fort.population"
FORT_ALERTS_COUNT = "fort.alerts.count"
FORT_STUCK_JOBS_COUNT = "fort.stuck_jobs.count"
FORT_LANDMARKS_COUNT = "fort.landmarks.count"
LANDMARK_EXISTS = "landmark.exists"
LANDMARK_EXIT_DISTANCE = "landmark.exit.distance_tiles"

#: `handoffs/2026-09-16-stocks-read-and-labor-race.md` item 2. Backed by
#: `stocks.food-drink` / `stocks.seeds` (`scripts/dfhack/df-overseer-stocks.lua`).
#: See this module's docstring, "The `stocks.*` signals", for why these read
#: `not item.flags.trader` under the hood rather than `not item.flags.foreign`.
STOCKS_DRINK_COUNT = "stocks.drink.count"
STOCKS_PREPARED_MEALS_COUNT = "stocks.prepared_meals.count"
STOCKS_RAW_EDIBLES_COUNT = "stocks.raw_edibles.count"
STOCKS_SEEDS_COUNT = "stocks.seeds.count"

SIGNAL_KINDS = (
    FORT_POPULATION, FORT_ALERTS_COUNT, FORT_STUCK_JOBS_COUNT,
    FORT_LANDMARKS_COUNT, LANDMARK_EXISTS, LANDMARK_EXIT_DISTANCE,
    STOCKS_DRINK_COUNT, STOCKS_PREPARED_MEALS_COUNT, STOCKS_RAW_EDIBLES_COUNT,
    STOCKS_SEEDS_COUNT,
)

VALUE_TYPE = {
    FORT_POPULATION: INTEGER,
    FORT_ALERTS_COUNT: INTEGER,
    FORT_STUCK_JOBS_COUNT: INTEGER,
    FORT_LANDMARKS_COUNT: INTEGER,
    LANDMARK_EXISTS: BOOLEAN,
    LANDMARK_EXIT_DISTANCE: INTEGER,
    STOCKS_DRINK_COUNT: INTEGER,
    STOCKS_PREPARED_MEALS_COUNT: INTEGER,
    STOCKS_RAW_EDIBLES_COUNT: INTEGER,
    STOCKS_SEEDS_COUNT: INTEGER,
}

#: Every live signal is MECHANICAL: read straight off a read tool's own
#: JSON, no judgement involved. Reused from `learning.ledger.schema` rather
#: than a second copy of the source vocabulary.
SOURCE = MECHANICAL


class SignalError(Exception):
    """Raised by `parse()` when a string does not name a known live signal."""


@dataclass(frozen=True)
class ParsedSignal:
    kind: str
    signal: str                    # the original dotted string, for messages/storage
    landmark: Optional[str] = None
    exit_to: Optional[str] = None

    @property
    def value_type(self) -> str:
        return VALUE_TYPE[self.kind]


# ---- parsing --------------------------------------------------------------------
#
# `_QUOTED` matches a double-quoted landmark name: any run of characters that
# are neither an unescaped `"` nor a lone `\`, or a `\` followed by any one
# character (covers `\"` and `\\`). This is deliberately a *string* grammar,
# not a full escaping language — the only two characters that ever need
# escaping inside a landmark name are `"` and `\` itself.

_QUOTED = r'"((?:[^"\\]|\\.)*)"'

_EXISTS_RE = re.compile(rf'^landmark\.{_QUOTED}\.exists$')
_EXIT_RE = re.compile(rf'^landmark\.{_QUOTED}\.exit\.{_QUOTED}\.distance_tiles$')

_FIXED_SIGNALS = {
    FORT_POPULATION: FORT_POPULATION,
    FORT_ALERTS_COUNT: FORT_ALERTS_COUNT,
    FORT_STUCK_JOBS_COUNT: FORT_STUCK_JOBS_COUNT,
    FORT_LANDMARKS_COUNT: FORT_LANDMARKS_COUNT,
    STOCKS_DRINK_COUNT: STOCKS_DRINK_COUNT,
    STOCKS_PREPARED_MEALS_COUNT: STOCKS_PREPARED_MEALS_COUNT,
    STOCKS_RAW_EDIBLES_COUNT: STOCKS_RAW_EDIBLES_COUNT,
    STOCKS_SEEDS_COUNT: STOCKS_SEEDS_COUNT,
}


def _unquote(raw: str) -> str:
    return raw.replace('\\"', '"').replace("\\\\", "\\")


def quote_landmark_name(name: str) -> str:
    """Escape `name` for embedding inside a `"..."` segment of a signal
    string. The inverse of the unescaping `parse()` does internally."""
    return name.replace("\\", "\\\\").replace('"', '\\"')


def parse(signal: Any) -> ParsedSignal:
    """Parse a dotted signal name.

    Raises `SignalError` if `signal` does not name a known live signal —
    never returns a partial or best-guess result. Purely syntactic: does
    not check that a named landmark currently exists (see the module
    docstring on why that is `read()`'s job, not this one's).
    """
    if not isinstance(signal, str) or not signal:
        raise SignalError(f"signal: expected a non-empty string, got {signal!r}")

    if signal in _FIXED_SIGNALS:
        return ParsedSignal(kind=_FIXED_SIGNALS[signal], signal=signal)

    m = _EXISTS_RE.match(signal)
    if m:
        return ParsedSignal(kind=LANDMARK_EXISTS, signal=signal, landmark=_unquote(m.group(1)))

    m = _EXIT_RE.match(signal)
    if m:
        return ParsedSignal(
            kind=LANDMARK_EXIT_DISTANCE, signal=signal,
            landmark=_unquote(m.group(1)), exit_to=_unquote(m.group(2)),
        )

    raise SignalError(
        f"signal {signal!r} is not a known live signal (fort.population, "
        "fort.alerts.count, fort.stuck_jobs.count, fort.landmarks.count, "
        'landmark."NAME".exists, landmark."NAME".exit."TO".distance_tiles, '
        "stocks.drink.count, stocks.prepared_meals.count, "
        "stocks.raw_edibles.count, stocks.seeds.count)"
    )


# ---- reading ----------------------------------------------------------------------

CallTool = Callable[[str, dict], Any]


class _Unresolvable:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "UNRESOLVABLE"


#: Returned by `read()` for a signal that cannot be resolved *right now* — a
#: landmark that doesn't exist yet, or an exit that doesn't (yet) appear in a
#: landmark's own ranked exit list. Distinct from a parse failure
#: (`SignalError`): a proposal may legitimately predict about something it
#: proposes to build (see the module docstring).
UNRESOLVABLE = _Unresolvable()


def _landmarks_list(call_tool: CallTool) -> list:
    """`landmarks.list`'s real success shape is a bare array; its real
    failure shape (no citizens found yet to seed a landmark set) is a
    `{"error": ...}` object instead — see `list_landmarks` in
    `df-overseer-landmarks.lua`. Treated as "no landmarks", not a crash."""
    result = call_tool("landmarks.list", {})
    if isinstance(result, list):
        return result
    return []


def read(parsed: ParsedSignal, call_tool: CallTool):
    """Read `parsed`'s current value via `call_tool(tool_id, arguments)`.

    `call_tool` must return the tool's own parsed JSON, in that tool's real
    shape (a dict for `overview.get`/`landmarks.get`, a bare list for
    `stuckjobs.find`/`landmarks.list`) — never a DFHack or MCP import
    happens here.
    """
    if parsed.kind == FORT_POPULATION:
        overview = call_tool("overview.get", {})
        return overview["tier1"]["population"]

    if parsed.kind == FORT_ALERTS_COUNT:
        overview = call_tool("overview.get", {})
        return len(overview["tier2"]["alerts"])

    if parsed.kind == FORT_STUCK_JOBS_COUNT:
        jobs = call_tool("stuckjobs.find", {})
        return len(jobs)

    if parsed.kind == FORT_LANDMARKS_COUNT:
        return len(_landmarks_list(call_tool))

    if parsed.kind == STOCKS_DRINK_COUNT:
        food_drink = call_tool("stocks.food-drink", {})
        return food_drink["drink"]["count"]

    if parsed.kind == STOCKS_PREPARED_MEALS_COUNT:
        food_drink = call_tool("stocks.food-drink", {})
        return food_drink["prepared_meals"]["count"]

    if parsed.kind == STOCKS_RAW_EDIBLES_COUNT:
        food_drink = call_tool("stocks.food-drink", {})
        return food_drink["raw_edibles"]["count"]

    if parsed.kind == STOCKS_SEEDS_COUNT:
        seeds = call_tool("stocks.seeds", {})
        return seeds["total"]

    if parsed.kind == LANDMARK_EXISTS:
        return any(lm.get("name") == parsed.landmark for lm in _landmarks_list(call_tool))

    if parsed.kind == LANDMARK_EXIT_DISTANCE:
        landmark = call_tool("landmarks.get", {"name": parsed.landmark})
        if not isinstance(landmark, dict) or landmark.get("error"):
            return UNRESOLVABLE  # landmark doesn't exist (yet)
        for exit_ in landmark.get("exits", []):
            if exit_.get("to") == parsed.exit_to:
                return exit_["distance_tiles"]
        return UNRESOLVABLE  # not (yet) in the landmark's own ranked exit list

    raise SignalError(f"read(): unhandled signal kind {parsed.kind!r}")  # pragma: no cover
