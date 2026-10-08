"""Native tools for the fort plan: `plan.write`, `plan.read`, `plan.status`.

`research/2026-10-07-planner-design.md` 2 (revision 2) and `handoffs/
2026-10-07-planner-p1a.md`. None calls a DFHack command to change anything;
they read and write `dfqueue`'s own database, and read the fort only to
validate and measure (`zone.list-kinds`, `landmarks.list`, the signals a
target names, `vitals.summary`, `stocks.availability`). Registered the same
way as every native tool (`dfmcp/queue_tools.py`, `dfmcp/conductor_tools.py`):
a `NativeTool` per id merged into the registry, dispatched by
`dfmcp/server.py`, enforced by the same `Roster.check` boundary plus a role
check here (two layers, never one).

## `plan.write` (the Planner only)

Takes `base_version` (0 before version 1) and only the **sections changed**
(`set`), a `reason`, optional `relies_on` (a tool field **or a live signal**,
so a zero can be cited, F-14), `public_rationale`, `ruling_id` and `dry_run`.
The server composes the full record from the active version (or
the fort roadmap's current-stage targets for version 1), refuses a `base_version` that is not
the active one (so a retry after a timeout is safe), stamps the version, the
season index and the server-computed `changes`, and **accepts and flags**
content mistakes: the reply lists every flag with repair text, and a flagged
entry is inert until fixed. Only a payload that cannot be stored is refused:
the wrong writer role, coordinates, a payload that is not the schema shape, a
section with no home yet. A dry run returns everything a real write would
(flags, changes, the season verdict) and writes nothing.

## The fort roadmap (register 2026-10-08, `fort_roadmap/`)

Every plan tool computes the fort's roadmap stage (`alive` with a stored
high-water mark, cross-checked against `nobles.list`'s population flags) and
returns it as a `roadmap` block. `plan.write` stamps `roadmap_stage` on the
version, computes the deviation of every `roadmap_ref` target from its stage
entry (flagged without a `deviation_reason`, never refused), and lets a
revision that only adopts a newly entered stage's targets skip the season
interval. `plan.status` (the conductor's per-cycle read) persists the stage
mark when it advances.

## `plan.read`

The active (or a named) version, one section, the last 8 version lines, and
optionally the computed target status. **Sliced by role**: the Planner,
Overseer and conductor see the whole plan; any other role sees only the
targets it owns or whose derived inputs it owns.

## `plan.status` (the conductor only)

Design F-4. Per target: `{signal, want, reorder or reorder_gap, owner,
on_hand, in_flight, serving, inputs, state}`, all computed here from records
and the live reads, so the conductor does arithmetic on nothing. `state` is
`open`, `quiet`, `unresolved` (a signal that cannot be read, never a
shortfall) or `inert` (the entry is flagged). The wake bookkeeping (renotify
backoff, `stalled`) belongs to the P1b shortfall watch and is not here.

## Not here

`in_flight` counts serving work until it finishes. The per-site rule of F-6
(a site counted only until its own zone is counted on hand) needs the
`site_handle -> zone` binding that arrives with districts (P2); until then a
finished project simply stops being in flight, and
`dfqueue.plan.target_position` takes the in-flight number the caller computed.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Tuple

from dfqueue import plan, schema, store, templates
from fort_roadmap import roadmap as fort_roadmap
from learning import live_signals

from . import queue_tools
from .queue_tools import QueueToolError

PLAN_WRITE = "plan.write"
PLAN_READ = "plan.read"
PLAN_STATUS = "plan.status"
NATIVE_TOOL_IDS = (PLAN_WRITE, PLAN_READ, PLAN_STATUS)

#: The conductor reads `plan.status`; the Planner writes. Named for the
#: handler's own role check (the second layer behind the allowlist).
STATUS_ROLE = schema.OBSERVATION_ROLE

FactReader = queue_tools.FactReader


class PlanToolError(QueueToolError):
    """A plan tool call is refused. A `QueueToolError` subclass so
    `dfmcp/server.py` turns it into an `isError` result like every other
    native tool's refusal."""


@dataclass(frozen=True)
class NativeTool:
    id: str
    mutates: bool = False
    sole_writer_only: bool = False
    native: bool = True
    args: Tuple[str, ...] = ()

    def describe(self, role: str) -> Tuple[str, dict]:
        del role
        return _DESCRIPTIONS[self.id], _SCHEMAS[self.id]


NATIVE_TOOLS: Dict[str, NativeTool] = {t: NativeTool(id=t) for t in NATIVE_TOOL_IDS}

# --------------------------------------------------------------------------
# Schemas and descriptions
# --------------------------------------------------------------------------

_TARGET_SCHEMA = {
    "type": "object",
    "description": (
        "One target: {id, signal, per, want, reorder or reorder_gap, owner, max_in_flight, note}. "
        "Mistakes are flagged by the server, not refused."
    ),
    "properties": {
        "id": {"type": "string"},
        "signal": {"type": "string", "description": 'e.g. zones."Bedroom".furnished'},
        "per": {"type": "string", "enum": list(plan.policy()["target"]["per"])},
        "want": {
            "description": (
                "a number (with per: alive it is per citizen), or a mapping {per_alive, plus, min, max}: "
                "wanted level = clamp(per_alive * alive + plus, min, max); give at least one of per_alive or plus"
            ),
            "oneOf": [
                {"type": "number"},
                {"type": "object", "properties": {k: {"type": "number"} for k in ("per_alive", "plus", "min", "max")}},
            ],
        },
        "reorder": {"type": "number", "description": "open when position is below this level (per citizen when per is alive; an absolute level with a mapping want)"},
        "reorder_gap": {"type": "number", "description": "open when this many units short of want"},
        "owner": {"type": "string", "description": "the role that serves the target"},
        "district": {"type": "string"},
        "max_in_flight": {"type": "integer"},
        "note": {"type": "string"},
        "roadmap_ref": {"type": "string", "description": "the id of the fort roadmap entry this target adopts (plan.read's roadmap block lists them)"},
        "deviation_reason": {"type": "string", "description": "why this target differs from its roadmap entry; without one a deviation is flagged (never refused)"},
    },
}

_WRITE_DESCRIPTION = (
    "File a new version of the fort plan, Planner only. Give base_version (the active version; 0 before "
    "version 1) and in `set` only the sections you change, each as its WHOLE new list (today: targets). "
    "The server composes the full plan, stamps the version and season, and computes `changes`. Mistakes "
    "(a kind typo, an unknown landmark, a bad signal or threshold, an oversized list) are ACCEPTED and "
    "FLAGGED in the reply, inert until you fix them; fixing only flagged entries is allowed at any time. "
    "One version per season; version 1 and a version citing an accepted plan_change ruling are exempt. "
    "Use dry_run=true first: it returns the flags, the changes and the season verdict and writes nothing. "
    "A reason is required from version 2. relies_on may cite a live signal ({signal}) or a read "
    "({tool, args, field}). Never a coordinate."
)

_WRITE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["base_version"],
    "properties": {
        "base_version": {"type": "integer", "minimum": 0},
        "set": {
            "type": "object",
            "description": "section name -> that section's whole new list",
            "properties": {"targets": {"type": "array", "items": _TARGET_SCHEMA}},
        },
        "reason": {"type": "string", "description": "why this version (required from version 2)"},
        "relies_on": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "signal": {"type": "string"}, "tool": {"type": "string"},
                "args": {"type": "object"}, "field": {"type": "string"},
            }},
        },
        "public_rationale": {"type": "string"},
        "ruling_id": {"type": "string", "description": "an accepted plan_change ruling that authorises a mid-season version"},
        "dry_run": {"type": "boolean"},
    },
}

_READ_DESCRIPTION = (
    "Read the fort plan: the active version (or `version`), one `section`, the last 8 version lines, and "
    "with status=true each target's computed position (on hand, in flight, state). You see the targets "
    "your role serves; the Planner sees them all. Before version 1 exists it returns the default plan "
    "to start from."
)

_READ_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "version": {"type": "integer", "minimum": 1},
        "section": {"type": "string", "enum": list(plan.policy()["open_sections"])},
        "status": {"type": "boolean"},
    },
}

_STATUS_DESCRIPTION = (
    "Conductor only. The active plan with every target's computed position: on hand, in flight, the "
    "serving proposals, derived inputs, state (open, quiet, unresolved, inert), per-owner in-flight use, "
    "accepted plan_change rulings awaiting the Planner, and the last review tick. Read-only."
)

_STATUS_SCHEMA: dict = {"type": "object", "additionalProperties": False, "properties": {}}

_DESCRIPTIONS = {PLAN_WRITE: _WRITE_DESCRIPTION, PLAN_READ: _READ_DESCRIPTION, PLAN_STATUS: _STATUS_DESCRIPTION}
_SCHEMAS = {PLAN_WRITE: _WRITE_SCHEMA, PLAN_READ: _READ_SCHEMA, PLAN_STATUS: _STATUS_SCHEMA}

_WRITE_FIELDS = set(_WRITE_SCHEMA["properties"])
_READ_FIELDS = set(_READ_SCHEMA["properties"])


# --------------------------------------------------------------------------
# World reads (each tolerant: a failed read is None, never a guess)
# --------------------------------------------------------------------------

CallDFHack = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


async def _try(call_dfhack: CallDFHack, tool_id: str, args: Mapping[str, Any]) -> Any:
    try:
        return await call_dfhack(tool_id, dict(args))
    except Exception:
        return None


def _rows(value: Any) -> Optional[list]:
    if isinstance(value, dict) and isinstance(value.get("result"), list):
        value = value["result"]
    return value if isinstance(value, list) else None


async def _context(call_dfhack: CallDFHack, sections: Mapping, relies_on: Any) -> plan.PlanContext:
    """The zone kind tokens and (only if a signal names one) the landmarks."""
    kinds = _rows(await _try(call_dfhack, "zone.list-kinds", {}))
    zone_kinds = {r.get("token") for r in kinds if isinstance(r, dict) and r.get("token")} if kinds is not None else None
    need_landmarks = False
    signals = [t.get("signal") for t in sections.get("targets") or [] if isinstance(t, dict)]
    signals += [r.get("signal") for r in relies_on or [] if isinstance(r, dict)]
    for sig in signals:
        try:
            parsed = live_signals.parse(sig)
        except live_signals.SignalError:
            continue
        if parsed.landmark is not None or parsed.exit_to is not None:
            need_landmarks = True
    landmarks = None
    if need_landmarks:
        rows = _rows(await _try(call_dfhack, "landmarks.list", {}))
        if rows is not None:
            landmarks = {r.get("name") for r in rows if isinstance(r, dict) and r.get("name")}
    return plan.PlanContext(zone_kinds=zone_kinds, landmarks=landmarks, roster_roles=set(schema._load_roster().get("roles", {})))


async def _read_signals(call_dfhack: CallDFHack, signals: list) -> Dict[str, Any]:
    """`{signal: number or None}`: each parsed signal read once through
    `learning.live_signals.read`. UNRESOLVABLE, an unparseable signal, a
    non-number and a failed read are all `None`. Run in a worker thread with
    each tool call handed back to this loop, the same bridge `queue.grade`
    uses."""
    loop = asyncio.get_running_loop()

    def sync_call_tool(tool_id: str, arguments):
        return asyncio.run_coroutine_threadsafe(call_dfhack(tool_id, dict(arguments)), loop).result()

    def run() -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for sig in dict.fromkeys(signals):
            try:
                value = live_signals.read(live_signals.parse(sig), sync_call_tool)
            except Exception:
                value = None
            ok = value is not live_signals.UNRESOLVABLE and isinstance(value, (int, float)) and not isinstance(value, bool)
            out[sig] = value if ok else None
        return out

    return await asyncio.to_thread(run)


async def _roadmap_block(db_path, call_dfhack: CallDFHack, persist: bool) -> dict:
    """The fort's roadmap block (`fort_roadmap.resolve`): `alive` from
    `vitals.summary`, the population flags from `nobles.list`, the stage mark
    stored beside the fort database. Each read tolerant: a failed one makes
    that part `unreadable`/unknown, never a guess."""
    vit = await _try(call_dfhack, "vitals.summary", {})
    alive = vit.get("alive") if isinstance(vit, dict) else None
    nobles = await _try(call_dfhack, "nobles.list", {})
    store_ = fort_roadmap.StageStore.beside(db_path)
    return await asyncio.to_thread(fort_roadmap.resolve, alive, nobles, store_, None, persist)


def _compact(structured: dict) -> str:
    return json.dumps(structured, sort_keys=True, default=str, ensure_ascii=False)


def _refuse_unknown(tool_id: str, arguments: Mapping[str, Any], known: set) -> None:
    queue_tools._reject_unknown_arguments(tool_id, arguments, known)


# --------------------------------------------------------------------------
# plan.write
# --------------------------------------------------------------------------


async def _citations(
    role: str, relies_on: Any, call_dfhack: CallDFHack, fact_reader: Optional[FactReader], tick: int,
) -> Tuple[list, list]:
    """`(cited, flags)`: each `relies_on` entry read now. A signal is read by
    `live_signals.read` (a zero is a number, F-14); a tool field by the same
    reader `queue.propose` uses. A read that fails is a flag and a null value,
    never a refusal."""
    cited: list = []
    flags: list = []
    if not isinstance(relies_on, list):
        return cited, flags
    sigs = [r["signal"] for r in relies_on if isinstance(r, dict) and isinstance(r.get("signal"), str)]
    values = await _read_signals(call_dfhack, sigs) if sigs else {}
    for i, ref in enumerate(relies_on):
        if not isinstance(ref, dict):
            cited.append({"value": None, "tick": tick})
            continue
        if "signal" in ref:
            value = values.get(ref.get("signal"))
            cited.append({"signal": ref.get("signal"), "value": value, "tick": tick})
            if value is None:
                flags.append(plan.flag(
                    "relies_on", f"#{i}", "unreadable_citation",
                    f"signal {ref.get('signal')!r} could not be read now; cited as null",
                ))
        elif isinstance(ref.get("tool"), str) and isinstance(ref.get("field"), str):
            try:
                value = await queue_tools.read_cited_fact(role, ref, fact_reader)
            except queue_tools.FactReadError as exc:
                value = None
                flags.append(plan.flag("relies_on", f"#{i}", "unreadable_citation", f"{exc}; cited as null"))
            cited.append({
                "tool": ref["tool"], "args": dict(ref.get("args") or {}), "field": ref["field"],
                "value": value, "tick": tick,
            })
        else:
            cited.append({"value": None, "tick": tick})
    return cited, flags


async def _write(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock", fact_reader: Optional[FactReader] = None,
) -> Tuple[str, dict]:
    if role != schema.PLAN_ROLE:
        raise PlanToolError(f"{PLAN_WRITE}: only the {schema.PLAN_ROLE!r} may write the fort plan")
    _refuse_unknown(PLAN_WRITE, arguments, _WRITE_FIELDS)
    base_version = arguments.get("base_version")
    if isinstance(base_version, bool) or not isinstance(base_version, int) or base_version < 0:
        raise PlanToolError(f"{PLAN_WRITE}: 'base_version' is required, an integer of 0 or more (0 before version 1)")
    dry_run = arguments.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise PlanToolError(f"{PLAN_WRITE}: 'dry_run' must be true or false")
    relies_on = arguments.get("relies_on")
    if relies_on is not None and not isinstance(relies_on, list):
        raise PlanToolError(f"{PLAN_WRITE}: 'relies_on' must be a list")

    tick, snapshot = await queue_tools._stamp_cycle_snapshot(call_dfhack)
    try:
        active = await asyncio.to_thread(store.active_plan, db_path)
    except (sqlite3.Error, OSError) as exc:
        raise queue_tools._storage_error(PLAN_WRITE, exc) from exc
    have = active["version"] if active else 0
    if base_version != have:
        raise PlanToolError(
            f"{PLAN_WRITE}: stale base: you sent base_version {base_version} but the active version is {have}. "
            "Read plan.read, then send your sections against the active version (a retry after a timeout "
            "may already have filed)."
        )
    block = await _roadmap_block(db_path, call_dfhack, persist=not dry_run)
    stage_id = block["stage"]
    base = plan.default_plan(stage_id) if active is None else None
    try:
        sections = plan.compose(active, arguments.get("set"), base)
    except plan.PlanShapeError as exc:
        raise PlanToolError(f"{PLAN_WRITE}: refused: {exc}") from exc

    base_sections = store._plan_base_sections(active, base)
    changes = plan.diff_changes(base_sections, sections)
    ctx = await _context(call_dfhack, sections, relies_on)
    flags = plan.check_sections(sections, ctx)
    flags += plan.check_text_fields(arguments.get("reason"), arguments.get("public_rationale"), relies_on, ctx)
    refs = fort_roadmap.check_refs(sections.get("targets") or [], stage_id, block.get("alive"))
    flags += refs["flags"]
    cited, cite_flags = await _citations(role, relies_on, call_dfhack, fact_reader, tick)
    flags += cite_flags

    record: dict = {
        "kind": schema.FORT_PLAN, "role": role, "cycle": tick, "snapshot": snapshot,
        "version": have + 1, "supersedes": active["id"] if active else None,
        "season_index": plan.season_index(tick), "changes": changes, "flags": flags,
        "roadmap_stage": stage_id, "deviations": refs["deviations"],
        **sections,
    }
    for name in ("reason", "public_rationale", "ruling_id"):
        if arguments.get(name) is not None:
            record[name] = arguments[name]
    if relies_on is not None:
        record["relies_on"] = relies_on
        record["cited"] = cited
    ruling_id = record.get("ruling_id")
    try:
        ruling_problem = (
            await asyncio.to_thread(store.plan_ruling_problem, db_path, ruling_id) if ruling_id else None
        )
    except (sqlite3.Error, OSError) as exc:
        raise queue_tools._storage_error(PLAN_WRITE, exc) from exc
    verdict = plan.guardrail(
        active, tick, changes, None if ruling_problem else ruling_id,
        adopt_stage=fort_roadmap.adopts_stage(active, changes, sections, stage_id),
    )
    if active is not None and not changes:
        verdict = {"ok": False, "reason": "no_change", "refusal": "nothing changes against the active version"}

    inert = sorted({f"{f['section']}.{f['id']}" for f in flags if f.get("inert") and f.get("id") is not None})
    structured: dict = {
        "version": record["version"], "season_index": record["season_index"], "tick": tick,
        "changes": changes, "flags": flags, "inert_entries": inert,
        "season": verdict,
        "roadmap": {
            "stage": stage_id, "entered": block.get("entered"), "deviations": refs["deviations"],
            "stage_entries_not_in_plan": refs["missing"], "cross_check": block.get("cross_check"),
        },
    }
    if ruling_problem:
        structured["ruling_problem"] = ruling_problem

    if dry_run:
        shape_errors = schema.validate(record)
        structured.update({
            "dry_run": True,
            "would_file": not shape_errors and verdict["ok"] and not ruling_problem,
            "refusals": shape_errors,
        })
        return _compact(structured), structured

    written = await queue_tools._append_locked(PLAN_WRITE, record, db_path, tick, write_lock)
    structured.update({"dry_run": False, "filed": True, "id": written["id"]})
    return _compact(structured), structured


# --------------------------------------------------------------------------
# target status (plan.read status=true, plan.status)
# --------------------------------------------------------------------------


async def _target_status(
    db_path, call_dfhack: CallDFHack, active: Mapping, only_role: Optional[str] = None,
) -> dict:
    """The computed position of every (visible) target: `{targets, owners,
    alive}`. All reads are made once and shared."""
    pol = plan.policy()
    targets = [t for t in active.get("targets") or [] if isinstance(t, dict)]
    inert = plan.inert_keys(active.get("flags") or [])
    if only_role is not None:
        targets = plan.slice_for_role(targets, only_role)
    live = [t for t in targets if ("targets", t.get("id")) not in inert]
    alive = None
    if any(plan.want_uses_alive(t) for t in live):
        vit = await _try(call_dfhack, "vitals.summary", {})
        v = vit.get("alive") if isinstance(vit, dict) else None
        alive = v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    readings = await _read_signals(call_dfhack, [t["signal"] for t in live if isinstance(t.get("signal"), str)])
    try:
        work = await asyncio.to_thread(store.serving_work, db_path)
    except (sqlite3.Error, OSError) as exc:
        raise queue_tools._storage_error(PLAN_STATUS, exc) from exc

    tpl_by_target: Dict[str, Optional[dict]] = {}
    for t in live:
        tpl_by_target[t["id"]] = templates.serving(t["signal"]) if isinstance(t.get("signal"), str) else None
    items_needed = sorted({r for tpl in tpl_by_target.values() if tpl for r in tpl["requires"]})
    avail: Dict[str, Optional[float]] = {}
    if items_needed:
        sigs = {
            item: f'stocks.availability."{live_signals.quote_landmark_name(plan.item_type(item))}".available_units'
            for item in items_needed
        }
        got = await _read_signals(call_dfhack, list(sigs.values()))
        avail = {item: got.get(sig) for item, sig in sigs.items()}

    out_targets = []
    owner_use: Dict[str, int] = {}
    for t in targets:
        tid = t.get("id")
        row: dict = {k: t[k] for k in ("id", "signal", "per", "want", "reorder", "reorder_gap", "owner", "max_in_flight") if k in t}
        serving = work.get(tid, [])
        row["serving"] = serving
        if ("targets", tid) in inert:
            row.update({"state": "inert", "flags": [f for f in active.get("flags") or [] if f.get("id") == tid and f.get("section") == "targets"]})
            out_targets.append(row)
            continue
        tpl = tpl_by_target.get(tid)
        units = tpl["units"] if tpl else 0
        in_flight = float(units) * len(serving)
        row.update(plan.target_position(t, readings.get(t["signal"]), in_flight, alive))
        cap = t.get("max_in_flight", pol["target"]["max_in_flight_default"])
        row["at_max_in_flight"] = len(serving) >= cap
        row["template"] = tpl["id"] if tpl else None
        if tpl and serving:
            row["inputs"] = plan.derived_inputs(tpl["requires"], float(len(serving)), avail, pol)
        else:
            row["inputs"] = []
        owner_use[t.get("owner")] = owner_use.get(t.get("owner"), 0) + len(serving)
        out_targets.append(row)
    return {
        "targets": out_targets, "alive": alive,
        "owners": {o: {"in_flight": n, "ceiling": pol["in_flight_per_owner"]} for o, n in sorted(owner_use.items(), key=lambda kv: str(kv[0]))},
    }


# --------------------------------------------------------------------------
# plan.read
# --------------------------------------------------------------------------


async def _read(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock", fact_reader: Optional[FactReader] = None,
) -> Tuple[str, dict]:
    _refuse_unknown(PLAN_READ, arguments, _READ_FIELDS)
    version = arguments.get("version")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version < 1):
        raise PlanToolError(f"{PLAN_READ}: 'version' must be a positive integer")
    section = arguments.get("section")
    if section is not None and section not in plan.policy()["open_sections"]:
        raise PlanToolError(f"{PLAN_READ}: 'section' must be one of {plan.policy()['open_sections']}")
    want_status = arguments.get("status", False)
    if not isinstance(want_status, bool):
        raise PlanToolError(f"{PLAN_READ}: 'status' must be true or false")
    try:
        active = await asyncio.to_thread(store.active_plan, db_path)
        chosen = active if version is None else await asyncio.to_thread(store.plan_version, db_path, version)
        history = await asyncio.to_thread(store.plan_history, db_path, plan.policy()["history_lines"])
        awaiting = await asyncio.to_thread(store.plan_changes_awaiting, db_path)
    except (sqlite3.Error, OSError) as exc:
        raise queue_tools._storage_error(PLAN_READ, exc) from exc

    if chosen is None:
        if version is not None:
            raise PlanToolError(f"{PLAN_READ}: there is no plan version {version}")
        block = await _roadmap_block(db_path, call_dfhack, persist=False)
        base = plan.default_plan(block["stage"])
        structured = {
            "active_version": 0,
            "note": (
                f"no plan has been filed; this is the fort roadmap's {block['stage']} stage to start from. "
                "File version 1 with plan.write base_version 0."
            ),
            "default": {s: base.get(s, []) for s in plan.policy()["open_sections"]},
            "history": [],
        }
        if role in (schema.PLAN_ROLE, schema.sole_writer()):
            structured["roadmap"] = block
        return _compact(structured), structured

    sliced_targets = plan.slice_for_role(chosen.get("targets") or [], role)
    visible = {t.get("id") for t in sliced_targets if isinstance(t, dict)}
    body: dict = {}
    for s in plan.policy()["open_sections"]:
        if section is None or section == s:
            body[s] = sliced_targets if s == "targets" else chosen.get(s, [])
    structured = {
        "active_version": active["version"], "version": chosen["version"], "id": chosen["id"],
        "season_index": chosen.get("season_index"), "reason": chosen.get("reason"),
        "ruling_id": chosen.get("ruling_id"), **body,
        "flags": [
            f for f in chosen.get("flags") or []
            if f.get("section") != "targets" or f.get("id") in visible or role == schema.PLAN_ROLE
        ],
        "history": [plan.version_line(r) for r in history],
    }
    if role in (schema.PLAN_ROLE, schema.sole_writer()) and awaiting:
        structured["plan_changes_awaiting"] = [
            {"proposal_id": a["proposal"]["id"], "ruling_id": a["ruling_id"]} for a in awaiting
        ]
    if role in (schema.PLAN_ROLE, schema.sole_writer()):
        block = await _roadmap_block(db_path, call_dfhack, persist=False)
        refs = fort_roadmap.check_refs(active.get("targets") or [], block["stage"], block.get("alive"))
        structured["roadmap"] = {
            **block, "plan_stage": active.get("roadmap_stage"), "deviations": refs["deviations"],
            "stage_entries_not_in_plan": refs["missing"],
        }
    if want_status:
        if version is not None and chosen["version"] != active["version"]:
            raise PlanToolError(f"{PLAN_READ}: status is computed only for the active version")
        structured["status"] = await _target_status(db_path, call_dfhack, active, only_role=role)
    return _compact(structured), structured


# --------------------------------------------------------------------------
# plan.status
# --------------------------------------------------------------------------


async def _status(
    role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock", fact_reader: Optional[FactReader] = None,
) -> Tuple[str, dict]:
    if role != STATUS_ROLE:
        raise PlanToolError(f"{PLAN_STATUS}: only the {STATUS_ROLE!r} may read plan status")
    _refuse_unknown(PLAN_STATUS, arguments, set())
    try:
        active = await asyncio.to_thread(store.active_plan, db_path)
        awaiting = await asyncio.to_thread(store.plan_changes_awaiting, db_path)
        reviewed = await asyncio.to_thread(store.plan_last_reviewed_tick, db_path)
    except (sqlite3.Error, OSError) as exc:
        raise queue_tools._storage_error(PLAN_STATUS, exc) from exc
    block = await _roadmap_block(db_path, call_dfhack, persist=True)
    structured: dict = {
        "roadmap": block,
        "active": None if active is None else {
            "id": active["id"], "version": active["version"], "season_index": active.get("season_index"),
            "tick": active.get("cycle"), "roadmap_stage": active.get("roadmap_stage"),
        },
        "bootstrap": active is None,
        "last_reviewed_tick": reviewed,
        "plan_changes_awaiting": [{"proposal_id": a["proposal"]["id"], "ruling_id": a["ruling_id"]} for a in awaiting],
    }
    if active is not None:
        structured.update(await _target_status(db_path, call_dfhack, active))
        structured["flags"] = [f for f in active.get("flags") or [] if f.get("inert")]
    return _compact(structured), structured


_HANDLERS = {PLAN_WRITE: _write, PLAN_READ: _read, PLAN_STATUS: _status}


async def call(
    tool_id: str, role: str, arguments: Mapping[str, Any], *, db_path, call_dfhack: CallDFHack,
    write_lock: "asyncio.Lock", fact_reader: Optional[FactReader] = None,
) -> Tuple[str, Optional[dict]]:
    """Dispatch one plan tool call. Raises `PlanToolError` (a
    `QueueToolError`) for `dfmcp.server` to turn into `isError=True`."""
    handler = _HANDLERS.get(tool_id)
    if handler is None:  # pragma: no cover -- the server routes only known ids here
        raise AssertionError(f"plan_tools.call: unknown native tool id {tool_id!r}")
    return await handler(
        role, arguments, db_path=db_path, call_dfhack=call_dfhack, write_lock=write_lock,
        fact_reader=fact_reader,
    )
