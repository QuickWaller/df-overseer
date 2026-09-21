"""The labor join: results from the generic building tool gain the labors that
operate the kind, joined in **by the server** from the production graph.

Design: `docs/BUILDING-TOOL.md`, open question 1 (option (b), decided
2026-09-21) and contracts **C1** (the Lua tool's output, live facts only, no
labor names) and **C2** (`production.labors.labors_for_kind`). The Lua tool
carries no labor field on purpose: a workshop's operating labors are the
labors of the processes it hosts in the graph's `production_process`, so the
graph is the one source. A raw command-line call to the Lua tool therefore
does not include them; only a call through this server does.

## What is added to a result

Three top-level siblings, next to whatever the tool printed:

- `operating_labors`: `{"status": "known" | "partial" | "unknown", "labors":
  [...] or null, "unknown_reason": str or null, "processes": [...] or null,
  "citizens_with_labor": {LABOR: n or null} or null,
  "citizens_with_labor_errors": {LABOR: message}}`.
- `gaps`: what is demonstrably missing, in plain words ("nobody has the
  BREWER labor enabled", "no BOULDER, WOOD or BLOCKS in the fort to build
  with").
- `gaps_unknown`: what could **not** be checked and why, in plain words.

## Unknown is not zero (the rule this file exists to keep)

The silent-zero bug class has shipped five times in this repo (register
2026-09-19). So:

- C2's `unknown` reaches the agent as `labors: null` and a `gaps_unknown`
  line, **never** as an empty list. C2's `partial` reaches the agent with the
  labors that are known, `status: "partial"`, and the reason. Only `known`
  with an empty list means "the game data says no labor applies".
- A count the Lua read could not make (C1's `null` plus an error) stays
  `null` with its error and lands in `gaps_unknown`; it is never read as 0 and
  so never produces the "nobody has this labor" gap.
- An absent graph database, an absent `production.labors` module (the graph
  stream not merged or not deployed), a lookup that raises, a result of an
  unexpected shape, a `requirements` block the joiner cannot read: each is
  `unknown` with the reason. None is an empty list and none is "no gaps".
- `gaps: []` together with `gaps_unknown: []` is the only "nothing is
  missing" answer, and it is only reachable when every check ran.

## Bookkeeping calls bypass `Roster.check`

The `enabled-counts` read is the server's own bookkeeping for building a
result the caller already had permission to request, like `queue_tools`'
`overview.get` stamp (see that module's docstring). It is issued through the
injected `count_labors`, not through the caller's grant.

## Testability

`labors_for_kind` and `count_labors` are injected. Production wires the real
`production.labors.labors_for_kind` (imported lazily so this module, and the
whole server, loads before that stream merges) and a DFHack call. Tests pin
the C2 contract with a stub.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

#: The DFHack-backed tool ids whose results are joined. Data, not a branch in
#: the server: the wrappers (`workshop.*`, `well.*`, `farm.*`) can be added
#: here when they are rebuilt over the generic tool.
LABOR_JOIN_TOOLS = ("building.find", "building.build")

#: Absolute and out of tree, same reasoning as `dfmcp.series_tools`. A plain
#: str because it is a Linux path and the workstation is Windows.
DEFAULT_PRODUCTION_DB_PATH = "/var/lib/dfproduction/uniboslan.production.sqlite3"

_LABOR_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_STATUSES = ("known", "partial", "unknown")

LaborsForKind = Callable[[str, str], Mapping[str, Any]]
CountLabors = Callable[[List[str]], Awaitable[Mapping[str, Any]]]


def _unknown(reason: str, extra_unknowns: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "operating_labors": {
            "status": "unknown",
            "labors": None,
            "unknown_reason": reason,
            "processes": None,
            "citizens_with_labor": None,
            "citizens_with_labor_errors": {},
        },
        "gaps": [],
        "gaps_unknown": [f"operating labors are unknown: {reason}", *(extra_unknowns or [])],
    }


def _import_labors_for_kind() -> LaborsForKind:
    from production import labors as production_labors  # lazy: see module docstring

    return production_labors.labors_for_kind


def _validate_c2(raw: Any) -> Optional[str]:
    """Why `raw` does not satisfy contract C2, or None."""
    if not isinstance(raw, Mapping):
        return f"the graph returned {type(raw).__name__}, not an object"
    if raw.get("status") not in _STATUSES:
        return f"the graph returned status {raw.get('status')!r}, not one of {list(_STATUSES)}"
    labors = raw.get("labors")
    if raw["status"] != "unknown":
        if not isinstance(labors, list) or not all(isinstance(x, str) for x in labors):
            return "the graph's 'labors' is not a list of names"
    return None


def _building_material_gaps(bm: Any, gaps: List[str], unknowns: List[str]) -> None:
    accepts = bm.get("accepts") if isinstance(bm, Mapping) else None
    owned = bm.get("fort_owned") if isinstance(bm, Mapping) else None
    if not (isinstance(accepts, list) and accepts and isinstance(owned, Mapping)):
        unknowns.append("the building_material requirement was present but not in a shape the server understands")
        return
    names = [str(a) for a in accepts]
    counts = [owned.get(n) for n in names]
    errors = bm.get("fort_owned_errors") if isinstance(bm.get("fort_owned_errors"), Mapping) else {}
    if any(isinstance(c, int) and not isinstance(c, bool) and c > 0 for c in counts):
        return
    unreadable = [n for n, c in zip(names, counts) if not (isinstance(c, int) and not isinstance(c, bool))]
    if unreadable:
        why = "; ".join(f"{n}: {errors.get(n) or 'no count returned'}" for n in unreadable)
        unknowns.append(f"could not count the building material ({why})")
        return
    gaps.append("no " + _or_list(names) + " in the fort to build with")


def _or_list(names: List[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " or " + names[-1]


def requirement_gaps(requirements: Any) -> Dict[str, List[str]]:
    """Plain-words gaps and unknowns from a C1 `requirements` block. Anything
    not understood is an unknown, never "no gap"."""
    gaps: List[str] = []
    unknowns: List[str] = []
    if requirements is None:
        unknowns.append("the result carried no requirements block")
    elif requirements == "unknown":
        unknowns.append("requirements are unknown for this kind (it has no requirements data entry)")
    elif not isinstance(requirements, Mapping):
        unknowns.append("the requirements block was not an object")
    else:
        if "building_material" in requirements:
            _building_material_gaps(requirements["building_material"], gaps, unknowns)
        container = requirements.get("needs_container")
        if container:
            owned = requirements.get("fort_owned_containers")
            if isinstance(owned, int) and not isinstance(owned, bool):
                if owned == 0:
                    gaps.append(f"the fort owns no {container}")
            else:
                err = requirements.get("fort_owned_containers_error")
                unknowns.append(f"could not count {container} ({err or 'no count returned'})")
    return {"gaps": gaps, "gaps_unknown": unknowns}


class LaborJoin:
    def __init__(
        self,
        production_db: str,
        count_labors: CountLabors,
        labors_for_kind: Optional[LaborsForKind] = None,
        tools=LABOR_JOIN_TOOLS,
    ):
        self.production_db = str(production_db)
        self._count_labors = count_labors
        self._labors_for_kind = labors_for_kind
        self.tools = tuple(tools)

    async def join(self, kind_token: Optional[str], requirements: Any) -> Dict[str, Any]:
        """The three sibling keys for one building result. Never raises."""
        req = requirement_gaps(requirements)
        if not kind_token:
            return _unknown("the result carried no kind token to look up", req["gaps_unknown"]) | {
                "gaps": req["gaps"]
            }

        fn = self._labors_for_kind
        if fn is None:
            try:
                fn = _import_labors_for_kind()
            except ImportError as exc:
                return _unknown(
                    f"production.labors is not available in this build ({exc})", req["gaps_unknown"]
                ) | {"gaps": req["gaps"]}
        try:
            raw = await asyncio.to_thread(fn, self.production_db, kind_token)
        except Exception as exc:  # the graph may be absent, locked, or mid-migration
            return _unknown(
                f"the production graph could not be read at {self.production_db}: "
                f"{type(exc).__name__}: {exc}",
                req["gaps_unknown"],
            ) | {"gaps": req["gaps"]}
        problem = _validate_c2(raw)
        if problem:
            return _unknown(problem, req["gaps_unknown"]) | {"gaps": req["gaps"]}

        status = raw["status"]
        if status == "unknown":
            reason = raw.get("unknown_reason") or "the graph gave no reason"
            return _unknown(reason, req["gaps_unknown"]) | {"gaps": req["gaps"]}

        labors = list(raw["labors"])
        gaps = list(req["gaps"])
        unknowns = list(req["gaps_unknown"])
        reason = raw.get("unknown_reason")
        if status == "partial":
            unknowns.append(
                "operating labors are only partly known"
                + (f": {reason}" if reason else "")
                + "; the labors listed may not be all of them"
            )
        processes = raw.get("processes")

        usable = [x for x in labors if _LABOR_NAME_RE.match(x)]
        for bad in [x for x in labors if not _LABOR_NAME_RE.match(x)]:
            unknowns.append(f"the graph named a labor {bad!r} that is not a labor token; not counted")

        counts: Optional[Dict[str, Optional[int]]] = None
        count_errors: Dict[str, str] = {}
        if usable:
            counts = {}
            try:
                got = await self._count_labors(usable)
            except Exception as exc:
                got = None
                for x in usable:
                    counts[x] = None
                    count_errors[x] = f"labor count read failed: {type(exc).__name__}: {exc}"
            if got is not None:
                got_counts = got.get("counts") if isinstance(got, Mapping) else None
                got_errors = got.get("errors") if isinstance(got, Mapping) else None
                if not isinstance(got_counts, Mapping):
                    got_counts, got_errors = {}, {}
                for x in usable:
                    value = got_counts.get(x)
                    if isinstance(value, int) and not isinstance(value, bool):
                        counts[x] = value
                    else:
                        counts[x] = None
                        msg = (got_errors or {}).get(x) if isinstance(got_errors, Mapping) else None
                        count_errors[x] = str(msg) if msg else "the labor count read returned no count"
            for x in usable:
                if counts[x] is None:
                    unknowns.append(f"could not count citizens with the {x} labor ({count_errors[x]})")
                elif counts[x] == 0:
                    gaps.append(f"nobody has the {x} labor enabled")

        return {
            "operating_labors": {
                "status": status,
                "labors": labors,
                "unknown_reason": reason if status == "partial" else None,
                "processes": processes if isinstance(processes, list) else None,
                "citizens_with_labor": counts,
                "citizens_with_labor_errors": count_errors,
            },
            "gaps": gaps,
            "gaps_unknown": unknowns,
        }


def render_xml(joined: Mapping[str, Any]) -> str:
    """The joined keys as one XML text block, the form a model reads best."""
    from xml.sax.saxutils import escape, quoteattr

    op = joined["operating_labors"]
    labors = op["labors"]
    lines = [f'<operating_context labor_status={quoteattr(op["status"])}>']
    if labors is None:
        lines.append(f"  <operating_labors unknown=\"true\">{escape(op['unknown_reason'] or '')}</operating_labors>")
    else:
        lines.append("  <operating_labors>")
        for name in labors:
            count = (op["citizens_with_labor"] or {}).get(name)
            shown = "unknown" if count is None else str(count)
            lines.append(f"    <labor name={quoteattr(name)} citizens_with_labor={quoteattr(shown)}/>")
        lines.append("  </operating_labors>")
        if op["status"] == "partial":
            lines.append(f"  <caution>{escape('operating labors only partly known: ' + (op['unknown_reason'] or ''))}</caution>")
    lines.append("  <gaps>")
    for gap in joined["gaps"]:
        lines.append(f"    <gap>{escape(gap)}</gap>")
    lines.append("  </gaps>")
    lines.append("  <gaps_unknown>")
    for item in joined["gaps_unknown"]:
        lines.append(f"    <unknown>{escape(item)}</unknown>")
    lines.append("  </gaps_unknown>")
    lines.append("</operating_context>")
    return "\n".join(lines)
