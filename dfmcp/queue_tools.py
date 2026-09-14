"""Native ("server-side") MCP tools: `queue.propose`, `queue.pass`,
`queue.rule`, `queue.pending`.

`docs/AGENT-ARCHITECTURE.md` §4: "A specialist cannot emit prose into the
queue. It calls `propose(...)` with typed fields, validated at write time,
and a malformed proposal is refused." `dfqueue/` (`dfqueue/schema.py`,
`dfqueue/store.py`) already builds that validation and storage; nothing
could call it. This module is the tool layer that closes the gap: a real
`propose(...)`, and its `pass`/`rule`/`pending` siblings, reachable as MCP
tool calls, with `dfmcp/server.py` as their one caller.

## Why these are not in `scripts/dfhack/TOOLS.yaml`

None of the four calls DFHack, runs a Lua script, or touches fort state at
all -- they read and write `dfqueue`'s own SQLite database. `registry.py`'s
canonical-id scheme and `tools.py`'s argv-construction heuristic both exist
specifically to turn a DFHack CLI signature into a JSON schema; neither
question is meaningful for a tool with no CLI signature. So these four are
defined here, by hand, as `NativeTool` objects with **explicit, hand-written
JSON schemas** (the brief's own requirement) -- never TOOLS.yaml's
`[BRACKETED]`/`UPPER_CASE` token heuristic -- and merged into the same
`dfmcp.registry.Registry` additively, via `registry.load_registry`'s
`native_tools=` kwarg, so `dfmcp.roles.Roster` enforces them through the
exact same `Roster.check(role, tool_id)` boundary as every DFHack tool
(the brief: "one boundary, not a second permission path").

## What a `NativeTool` needs to satisfy, and why

`dfmcp.roles._load_role_permissions` and `dfmcp.tools.tool_definitions` both
touch a registry entry generically (duck-typed, never `isinstance`-checked
against `dfmcp.registry.Tool`):

- `.mutates` (bool) -- roles.py rule 2 ("advisors are read-only"). Always
  `False` here: a queue write is a write to `dfqueue`'s own ledger, never a
  write to the fort DFHack simulates. Keeping `Tool.mutates` meaning
  *exactly* "mutates fort state" (never widened to "writes something,
  anything") is a hard line in this stream's brief, so an advisor holding
  `queue.propose` does not contradict "advisors are read-only".
- `.sole_writer_only` (bool) -- a new roles.py rule (rule 6) this stream
  added, independent of `.mutates`: `queue.rule` may only be granted to the
  roster's `sole_writer`. `dfqueue.schema.validate` enforces the same
  restriction again at write time (`record.role` for a `ruling`), so a
  misconfigured roster is caught at load time and a call that somehow got
  through anyway (a future bug in `Roster.check`) is still caught at the
  data layer. Two independent layers, deliberately not one.
- `.args` (empty list) -- so a generic sweep over `registry.all()` written
  for DFHack tools (`dfmcp/tests/test_tools.py`'s argument-token sweep)
  degrades to "nothing to check" rather than an `AttributeError`.
- `.native` (`True`) and `.describe(role)` -- `dfmcp.tools.tool_definitions`
  checks `hasattr(tool, "describe")` and, if present, calls it instead of
  the DFHack-shaped `_tool_description`/`_input_schema` pair. `describe`
  takes `role` because `queue.propose`'s schema is role-dependent (its
  `type` enum is that role's own closed proposal-type vocabulary,
  `dfqueue.schema.TYPE_VOCAB_BY_ROLE`); the other three ignore it.

## `role`/`id`/`ts`/`cycle`/`snapshot` are never tool arguments

Per the brief: "The record's `role` is the authenticated role
(`_current_role()`). `role`, `id`, `ts` must not be tool arguments at all,
so a caller cannot even attempt to set them." Every schema below sets
`"additionalProperties": false` and lists only the fields a caller may
actually supply (never `role`/`id`/`ts`/`cycle`/`snapshot`) -- but a client
is not obliged to validate against the schema it was handed, so the real
enforcement is in code: every handler below computes its own `known`
argument set and refuses (does not silently drop) anything outside it,
`role` included. `call()`'s own `role` parameter always comes from
`dfmcp.server._current_role()`, the authenticated identity, never from the
arguments dict.

## `cycle`/`snapshot`: a stand-in, not a scheduler

Every queue record needs `cycle` and `snapshot`
(`dfqueue.schema.COMMON_FIELDS`), and per `docs/AGENT-ARCHITECTURE.md` §5
both are meant to name one canonical, shared read of the world -- "stamped
with the game tick... immutable... every specialist in that cycle reads
only from it" -- produced by a Projection component that does not exist yet
(§2's table still marks Projection "not started"). Building that scheduler
is explicitly out of scope for this stream. The stand-in here: `cycle` is
stamped as the fort's current absolute game tick
(`dfqueue.grade.game_tick_from_overview`, read live through the same
`overview.get` call `queue.propose`'s prediction already needs), and
`snapshot` as the string `f"tick-{cycle}"`. This is honest in the sense the
brief asked for -- real, monotonic, mechanically read from the live game,
never a guess or a wall-clock stand-in -- but it is not yet a
scheduler-assigned round number, and every write (not only `queue.propose`)
now needs DFHack reachable to be written at all, which is a real behaviour
change worth knowing about, not only a documentation note (see this
stream's report). Revisit both fields' meaning when Projection exists.

## The internal DFHack call bypasses `Roster.check`

`_stamp_cycle_snapshot` below calls `overview.get` directly through the
injected `call_dfhack`, never through `Roster.check(role, "overview.get")`.
This is deliberate: stamping `cycle`/`snapshot` is `dfmcp.server`'s own
bookkeeping to make a valid record, not a call being made *on the caller's
behalf* under the caller's own grant -- the caller never sees this call, is
never billed a tool result for it, and could not distinguish it from any
other part of the write path. (In practice every role that can reach a
queue-write tool today also holds `overview.get` directly, so this
distinction is not yet load-bearing -- but it would matter the day a role
could write to the queue without also being allowed to read `overview.get`,
and the design should not quietly depend on that coincidence.)

## SQLite runs off the event loop, and writes are serialised

Added Phase A review, 2026-09-15, closing a gap the first pass of this
module left open: every `dfqueue.store` call here runs inside
`asyncio.to_thread`, not directly on the event loop -- a synchronous
SQLite call blocks whatever else that loop is doing (every other in-flight
MCP session on this same server process) for its whole duration.

Moving store calls onto a thread pool introduces a real race that a purely
synchronous call never had a chance to hit: `dfqueue.store._next_id` is
`COUNT(*)`-based and runs, along with the existing-id check, in a separate
read *before* the row it names is actually inserted -- fine when nothing
ever yields between the two, which is exactly what made the original
synchronous version accidentally safe. Once `append()` can run
concurrently on different threads, two proposals racing through
`_next_id` at the same moment can compute the same id, and the second
`INSERT` then fails on the `records.id` primary key -- a real,
reproducible collision, not a theoretical one (see
`dfmcp/tests/test_queue_tools.py`'s `test_concurrent_raw_appends_without_serialization_can_collide`,
which forces exactly this with a monkeypatched slow `_next_id`).

The fix: `call()` below takes a `write_lock: asyncio.Lock`, supplied by
the caller (`dfmcp/server.py`'s `build_mcp_server` creates exactly one per
running server and passes it down, matching how `pool`/`registry`/`roster`
are already scoped one per server build rather than a process-wide
global -- deliberately NOT a module-level lock here, since an
`asyncio.Lock` binds to whichever event loop first acquires it and raises
if reused from a different one, which a module-level singleton would be
the moment more than one event loop -- one real server process, or one
test after another -- ever touched it). It is held **only** around the
`asyncio.to_thread(store.append, ...)` call itself, in `_append_locked`
below. It is deliberately **not** held around `_stamp_cycle_snapshot`'s
`overview.get` call: DFHack latency under load has been observed in the
40-80 second range (this project's own operational history), and holding
a write lock across that would serialise every queue write in the fort
behind whichever one happens to be waiting on DFHack, turning an
occasional slow call into a pile-up. `queue.pending`'s read
(`store.pending_proposals`) also moves onto `asyncio.to_thread` for the
same off-loop reason, but takes no lock: it is a plain read, and the race
above is specific to the `_next_id`/insert sequence inside `append()`.

## Storage errors are refusals too, not crashes

Added the same review pass: a `sqlite3.Error` (a locked or corrupt
database, a schema mismatch) or `OSError` (an unwritable or missing queue
directory -- exactly the `ProtectSystem=strict`/`ReadWritePaths` gotcha
this stream's own Phase B checklist flags) raised by `dfqueue.store` used
to propagate straight out of `dfmcp.server._handle_call_tool` as an
unhandled exception -- a protocol-level failure, not the `isError=True`
tool result every other refusal in this package already is. Every store
call below is now wrapped to catch `(sqlite3.Error, OSError)` alongside
`store.QueueError` and re-raise as `QueueToolError`, via `_storage_error`.
The message names the tool id and the exception's own text, never the
`db_path` value itself in isolation as anything resembling a secret (it
is a local filesystem path, not a credential) -- but it also never echoes
`arguments`, which the caller already knows, so nothing new leaks either.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Tuple

from dfqueue import grade, render, schema, store
from learning import live_signals
from learning.predictions.schema import PREDICATE_OPS

CallDFHack = Callable[[str, Mapping[str, Any]], Awaitable[Any]]

# --------------------------------------------------------------------------
# Tool ids
# --------------------------------------------------------------------------

QUEUE_PROPOSE = "queue.propose"
QUEUE_PASS = "queue.pass"
QUEUE_RULE = "queue.rule"
QUEUE_PENDING = "queue.pending"

NATIVE_TOOL_IDS = (QUEUE_PROPOSE, QUEUE_PASS, QUEUE_RULE, QUEUE_PENDING)


class QueueToolError(Exception):
    """A queue tool call is refused: bad arguments, a `dfqueue.store.QueueError`
    (write-time validation, a duplicate id, a dangling `proposal_id`, a
    second final ruling), DFHack being unreachable while stamping
    `cycle`/`snapshot`, or a `sqlite3.Error`/`OSError` from the queue
    database itself (an unwritable directory, a locked or corrupt file --
    see this module's docstring, "Storage errors are refusals too, not
    crashes"). Always caught by `dfmcp.server` and turned into an MCP tool
    result with `isError=True` carrying this exception's message -- never
    raised past that boundary, matching how `dfmcp.tools.ArgumentError` and
    `dfmcp.roles.Roster.check` denials are already handled
    (`dfmcp/server.py`'s "Denials" note)."""


# --------------------------------------------------------------------------
# NativeTool: what registry.py and roles.py need, duck-typed against Tool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeTool:
    """See this module's docstring for exactly which attributes
    `dfmcp.roles`/`dfmcp.tools` read and why each is shaped the way it is."""

    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()

    def describe(self, role: str) -> Tuple[str, dict]:
        if self.id == QUEUE_PROPOSE:
            return _propose_description(role), _propose_schema(role)
        if self.id == QUEUE_PASS:
            return _PASS_DESCRIPTION, _PASS_SCHEMA
        if self.id == QUEUE_RULE:
            return _RULE_DESCRIPTION, _RULE_SCHEMA
        if self.id == QUEUE_PENDING:
            return _PENDING_DESCRIPTION, _PENDING_SCHEMA
        raise AssertionError(f"NativeTool.describe: unknown id {self.id!r}")  # pragma: no cover


NATIVE_TOOLS: Dict[str, NativeTool] = {
    QUEUE_PROPOSE: NativeTool(id=QUEUE_PROPOSE, mutates=False, sole_writer_only=False),
    QUEUE_PASS: NativeTool(id=QUEUE_PASS, mutates=False, sole_writer_only=False),
    QUEUE_RULE: NativeTool(id=QUEUE_RULE, mutates=False, sole_writer_only=True),
    QUEUE_PENDING: NativeTool(id=QUEUE_PENDING, mutates=False, sole_writer_only=False),
}


# --------------------------------------------------------------------------
# Schemas and descriptions: hand-written, teaching the §4 format directly
# --------------------------------------------------------------------------


def _signal_grammar_description() -> str:
    """Built from `learning.live_signals`'s own constants, not a hand-copied
    list that could drift out of sync with it (the brief's own requirement).
    The four fixed names come straight from `SIGNAL_KINDS`/`VALUE_TYPE`; only
    the two templated (landmark-quoted) forms are prose here, because they
    are not literal signal strings themselves."""
    fixed = ", ".join(
        f"{kind!r} ({live_signals.VALUE_TYPE[kind]})"
        for kind in live_signals.SIGNAL_KINDS
        if kind not in (live_signals.LANDMARK_EXISTS, live_signals.LANDMARK_EXIT_DISTANCE)
    )
    exists_type = live_signals.VALUE_TYPE[live_signals.LANDMARK_EXISTS]
    exit_type = live_signals.VALUE_TYPE[live_signals.LANDMARK_EXIT_DISTANCE]
    return (
        "A live, mid-fort signal (learning/live_signals.py) -- never a raw "
        "coordinate, never an end-of-fort learning/ledger field. Either one "
        f"of the fixed names {fixed}, or a landmark-templated form: "
        f'landmark."NAME".exists ({exists_type}) or '
        f'landmark."NAME".exit."TO".distance_tiles ({exit_type}), where NAME/TO '
        "are real landmark names in double quotes (escape a literal \" as \\\" "
        "and a literal \\ as \\\\). A signal naming an end-of-fort ledger field "
        "(e.g. design.entrance_count) is refused: that belongs in a "
        "learning/predictions/ record, not a dfqueue proposal."
    )


def _propose_description(role: str) -> str:
    vocab = schema.TYPE_VOCAB_BY_ROLE.get(role, ())
    vocab_text = ", ".join(vocab) if vocab else "(none -- this role does not propose)"
    return (
        "Write a proposal to the fort's decision queue (dfqueue), validated at "
        "write time: a malformed call is refused (isError) listing every "
        "problem found, and nothing is written. This is the only way to "
        "record a decision -- prose in your final answer is never read into "
        "the queue. role/id/ts/cycle/snapshot are stamped by the server; do "
        f"not pass them. Your closed `type` vocabulary: {vocab_text}."
    )


def _propose_schema(role: str) -> dict:
    vocab = list(schema.TYPE_VOCAB_BY_ROLE.get(role, ()))
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "type", "summary", "rationale", "prediction", "cost",
            "suggested_priority", "preconditions", "public_rationale",
        ],
        "properties": {
            "type": {
                "type": "string",
                "enum": vocab,
                "description": "This role's own closed proposal-type vocabulary.",
            },
            "summary": {
                "type": "string",
                "description": "A short, coordinate-free description of the proposed action.",
            },
            "rationale": {
                "type": "string",
                "description": (
                    "Why, in enough detail for the Overseer to judge it against "
                    "other proposals. Coordinate-free."
                ),
            },
            "prediction": {
                "type": "object",
                "additionalProperties": False,
                "required": ["signal", "op", "check_after_ticks"],
                "properties": {
                    "signal": {"type": "string", "description": _signal_grammar_description()},
                    "op": {
                        "type": "string",
                        "enum": list(PREDICATE_OPS),
                        "description": (
                            "A predicate operator. 'exists'/'not_exists' take no "
                            "`value`; every other op requires one."
                        ),
                    },
                    "value": {
                        "description": (
                            "Required unless op is 'exists'/'not_exists', in which case "
                            "it must be omitted entirely. Integer or boolean, matching "
                            "the signal's own declared type."
                        )
                    },
                    "check_after_ticks": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "How many game ticks after this proposal is written to check "
                            "the prediction, relative to the write-time game tick (not an "
                            "absolute tick)."
                        ),
                    },
                },
            },
            "cost": {
                "type": "object",
                "additionalProperties": False,
                "required": ["estimate", "unit"],
                "properties": {
                    "estimate": {"type": "number", "exclusiveMinimum": 0, "description": "Must be > 0."},
                    "unit": {"type": "string", "enum": list(schema.COST_UNITS)},
                },
            },
            "suggested_priority": {
                "type": "integer",
                "minimum": 1,
                "maximum": 7,
                "description": (
                    "1 (lowest) to 7 (highest). Advisory only -- the Overseer decides "
                    "the real ordering."
                ),
            },
            "preconditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["state"],
                    "properties": {
                        "landmark": {
                            "type": "string",
                            "description": "Exactly one of landmark or area is required, never both.",
                        },
                        "area": {"type": "string"},
                        "state": {
                            "type": "string",
                            "description": (
                                "What must still be true of the landmark/area for this "
                                "proposal to apply at execution time."
                            ),
                        },
                    },
                },
                "description": (
                    "Re-checked by the action tool at execution time (optimistic "
                    "concurrency); write what must still hold."
                ),
            },
            "public_rationale": {
                "type": "string",
                "description": (
                    "The only reasoning field ever published to the public feed. "
                    "Coordinate-free."
                ),
            },
        },
    }


_PASS_DESCRIPTION = (
    "Explicitly decline to propose anything this cycle, recorded in dfqueue "
    "rather than silently doing nothing ('a cycle with no proposal is a valid "
    "cycle'). role/id/ts/cycle/snapshot are stamped by the server; do not pass "
    "them."
)
_PASS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reason"],
    "properties": {
        "reason": {"type": "string", "description": "Why nothing is proposed this cycle. Coordinate-free."},
    },
}

_RULE_DESCRIPTION = (
    "Rule on one pending proposal: accept, reject or defer. Only the roster's "
    "sole writer may call this (enforced at load time in dfmcp.roles and again "
    "at write time in dfqueue.schema). role/id/ts/cycle/snapshot are stamped "
    "by the server; do not pass them."
)
_RULE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposal_id", "decision", "reason", "public_rationale"],
    "properties": {
        "proposal_id": {
            "type": "string",
            "description": "The id of an existing proposal record in this queue (see queue.pending).",
        },
        "decision": {"type": "string", "enum": list(schema.RULING_DECISIONS)},
        "reason": {"type": "string", "description": "Coordinate-free."},
        "public_rationale": {
            "type": "string",
            "description": (
                "The only reasoning field ever published to the public feed. Coordinate-free."
            ),
        },
    },
}

_PENDING_DESCRIPTION = (
    "Read-only: every proposal in this queue with no ruling yet, rendered as "
    "XML (the §4 prompt form), oldest first."
)
_PENDING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "description": "Return at most this many pending proposals. Omit for all of them.",
        },
    },
}


# --------------------------------------------------------------------------
# cycle/snapshot stamping
# --------------------------------------------------------------------------


async def _stamp_cycle_snapshot(call_dfhack: CallDFHack) -> Tuple[int, str]:
    """See module docstring, "cycle/snapshot: a stand-in, not a scheduler".
    Refuses (QueueToolError) rather than guessing if DFHack is unreachable or
    `overview.get`'s `in_game_date` does not parse -- never a wall-clock or
    process-local fallback."""
    try:
        overview = await call_dfhack("overview.get", {})
    except Exception as exc:  # the injected call_dfhack's own exception types
        raise QueueToolError(
            f"cannot stamp this record's cycle/snapshot: DFHack is unreachable: {exc}"
        ) from exc
    try:
        tick = grade.game_tick_from_overview(overview)
    except (KeyError, TypeError, ValueError) as exc:
        raise QueueToolError(
            f"cannot stamp this record's cycle/snapshot: overview.get's in_game_date "
            f"did not parse: {exc}"
        ) from exc
    return tick, f"tick-{tick}"


def _reject_unknown_arguments(tool_id: str, arguments: Mapping[str, Any], known: set) -> None:
    """The real enforcement behind 'role/id/ts/cycle/snapshot are stamped by
    the server; do not pass them': `additionalProperties: false` in the
    schema is defence in depth, not the boundary -- a client is not obliged
    to validate against the schema it was handed. This function is what a
    test can actually prove refuses a supplied `role` (or `id`/`ts`/`cycle`/
    `snapshot`, or any other stray key), and it writes nothing before the
    caller ever reaches `store.append`."""
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise QueueToolError(
            f"{tool_id}: unexpected argument(s) {unknown}; role/id/ts/cycle/snapshot "
            "are stamped by the server and must not be supplied, and this tool "
            f"accepts only {sorted(known)}"
        )


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------

_PROPOSE_FIELDS = {
    "type", "summary", "rationale", "prediction", "cost",
    "suggested_priority", "preconditions", "public_rationale",
}
_PASS_FIELDS = {"reason"}
_RULE_FIELDS = {"proposal_id", "decision", "reason", "public_rationale"}
_PENDING_FIELDS = {"limit"}


def _write_error(tool_id: str, exc: store.QueueError) -> QueueToolError:
    return QueueToolError(f"{tool_id}: {exc}")


def _storage_error(tool_id: str, exc: BaseException) -> QueueToolError:
    """A `sqlite3.Error`/`OSError` from `dfqueue.store`, wrapped the same
    way a write-time validation refusal already is -- see this module's
    docstring, "Storage errors are refusals too, not crashes"."""
    return QueueToolError(f"{tool_id}: the queue database is unavailable: {exc}")


async def _append_locked(
    tool_id: str, record: dict, db_path, game_tick: Optional[int], write_lock: "asyncio.Lock",
) -> dict:
    """`store.append`, off the event loop and serialised against every
    other write this server makes, per this module's docstring. Raises
    `QueueToolError` (never a raw `store.QueueError`/`sqlite3.Error`/
    `OSError`) so every caller below can `await` this directly with no
    try/except of its own."""
    try:
        async with write_lock:
            return await asyncio.to_thread(store.append, record, db_path, game_tick=game_tick)
    except store.QueueError as exc:
        raise _write_error(tool_id, exc) from exc
    except (sqlite3.Error, OSError) as exc:
        raise _storage_error(tool_id, exc) from exc


async def _propose(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock",
) -> Tuple[str, dict]:
    _reject_unknown_arguments(QUEUE_PROPOSE, arguments, _PROPOSE_FIELDS)
    tick, snapshot = await _stamp_cycle_snapshot(call_dfhack)
    record = {
        "kind": schema.PROPOSAL, "role": role, "cycle": tick, "snapshot": snapshot,
        **{k: arguments[k] for k in _PROPOSE_FIELDS if k in arguments},
    }
    written = await _append_locked(QUEUE_PROPOSE, record, db_path, tick, write_lock)
    return render.to_xml(written), written


async def _pass_(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock",
) -> Tuple[str, dict]:
    _reject_unknown_arguments(QUEUE_PASS, arguments, _PASS_FIELDS)
    tick, snapshot = await _stamp_cycle_snapshot(call_dfhack)
    record = {
        "kind": schema.PASS, "role": role, "cycle": tick, "snapshot": snapshot,
        **{k: arguments[k] for k in _PASS_FIELDS if k in arguments},
    }
    written = await _append_locked(QUEUE_PASS, record, db_path, tick, write_lock)
    return render.to_xml(written), written


async def _rule(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock",
) -> Tuple[str, dict]:
    _reject_unknown_arguments(QUEUE_RULE, arguments, _RULE_FIELDS)
    tick, snapshot = await _stamp_cycle_snapshot(call_dfhack)
    record = {
        "kind": schema.RULING, "role": role, "cycle": tick, "snapshot": snapshot,
        **{k: arguments[k] for k in _RULE_FIELDS if k in arguments},
    }
    written = await _append_locked(QUEUE_RULE, record, db_path, tick, write_lock)
    return render.to_xml(written), written


async def _pending(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock",
) -> Tuple[str, dict]:
    _reject_unknown_arguments(QUEUE_PENDING, arguments, _PENDING_FIELDS)
    limit = arguments.get("limit")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise QueueToolError(f"{QUEUE_PENDING}: 'limit' must be a positive integer, got {limit!r}")
    # No write_lock here on purpose: a plain read, not part of the
    # _next_id/insert race the lock exists to serialise (module docstring).
    try:
        records = await asyncio.to_thread(store.pending_proposals, db_path, limit=limit)
    except (sqlite3.Error, OSError) as exc:
        raise _storage_error(QUEUE_PENDING, exc) from exc
    xml = "\n\n".join(render.to_xml(r) for r in records) if records else "<pending/>"
    structured = {"count": len(records), "proposal_ids": [r["id"] for r in records]}
    return xml, structured


_HANDLERS = {
    QUEUE_PROPOSE: _propose,
    QUEUE_PASS: _pass_,
    QUEUE_RULE: _rule,
    QUEUE_PENDING: _pending,
}


async def call(
    tool_id: str, role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock",
) -> Tuple[str, Optional[dict]]:
    """Dispatch one native tool call. Returns `(text, structured)` for
    `dfmcp.server` to wrap into a `CallToolResult(isError=False, ...)`, or
    raises `QueueToolError` for `dfmcp.server` to turn into
    `isError=True`. Never called for an id outside `NATIVE_TOOL_IDS` --
    `dfmcp.server` only reaches this after confirming `registry.get(tool_id)`
    is a native tool.

    `write_lock`: one `asyncio.Lock` per running server, supplied by the
    caller (never constructed here -- see this module's docstring on why a
    module-level lock would be wrong). Only `_propose`/`_pass_`/`_rule`
    actually acquire it (inside `_append_locked`); `_pending` accepts and
    ignores it so every handler shares one call signature.
    """
    handler = _HANDLERS.get(tool_id)
    if handler is None:  # pragma: no cover -- server.py only routes known native ids here
        raise AssertionError(f"queue_tools.call: unknown native tool id {tool_id!r}")
    return await handler(role, arguments, db_path=db_path, call_dfhack=call_dfhack, write_lock=write_lock)
