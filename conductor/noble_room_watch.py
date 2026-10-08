"""Noble rooms: a position holder owns no room their position requires.

User decision 2026-10-08 (evals/live/2026-10-08-manager-appointment/README.md
Phase D): the Overseer appointed a manager unaided and could not give them an
office. Giving a noble the room their position needs is a routed
`zone.assign-owner` step the Architect files, usually as a follow-up joined to
the project that builds or furnishes that room. This watch is the signal that
wakes the Architect (`noble_room_unmet`); it files and changes nothing.

The signal, per (position code, holder, room kind)
--------------------------------------------------
`nobles.list` names the held positions; `nobles.requirements CODE` reports, per
room kind the position requires (Office, Bedroom, DiningHall, Tomb), a status.
The signal is a room-value status in policy `noble_room.statuses` (default
`not_met`) **and** the holder owning no zone of that kind (the read names the
owned zones in `zone_ids`; absent means none). A holder who owns a zone that
merely lacks its furniture is a building matter, not an ownership one, and is
not this signal. `cannot_tell` is never a signal: a quiet read is not evidence.

What the line gives the Architect: position, holder (unit id and name), room
kind, and the zone ids of that kind that exist with no owner (`zone.list`
`kind_filter`, `owner_filter=unowned`), so the common case needs no read.

Not woken while covered
-----------------------
An open proposal or project step whose tool is `zone.assign-owner` for this
holder's unit id already covers it (`queue.overview` `open_steps_for`). If that
coverage read fails the wake goes ahead (the store's structural duplicate
refusal is the backstop), since a silent suppression on a failed read would hide
the very case this exists for.

Generic over positions and room kinds: nothing here names a position or a kind.
Policy (statuses, backoff, how many positions are read) is in policy.yaml.
This module never writes anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, List, Mapping, Optional, Sequence, Tuple

#: Reads the watch makes (agents/conductor/tools.yaml).
LIST_TOOL = "nobles.list"
REQUIREMENTS_TOOL = "nobles.requirements"
ZONE_LIST_TOOL = "zone.list"
#: The step tool that gives a zone an owner; coverage looks for open steps of it.
ASSIGN_TOOL = "zone.assign-owner"

MAX_LINE_CHARS = 300
#: Unowned zone ids named in a line before "+N more".
MAX_ZONES_NAMED = 5


@dataclass(frozen=True)
class NobleRoomItem:
    position: str
    unit_id: int
    holder: str
    kind: str
    #: Zone ids of this kind with no owner, or None when the zone read failed.
    unowned_zones: Optional[Tuple[int, ...]] = None

    @property
    def key(self) -> str:
        return f"{self.position}:{self.unit_id}:{self.kind}"

    def line(self) -> str:
        who = f"{self.position} held by unit {self.unit_id}" + (f" ({self.holder})" if self.holder else "")
        head = f"{who} owns no {self.kind} zone, which the position requires"
        if self.unowned_zones is None:
            tail = "; unowned zones could not be read (zone.list)"
        elif not self.unowned_zones:
            tail = f"; no unowned {self.kind} zone exists, so one must be built first"
        else:
            named = ", ".join(str(z) for z in self.unowned_zones[:MAX_ZONES_NAMED])
            more = len(self.unowned_zones) - MAX_ZONES_NAMED
            tail = f"; unowned {self.kind} zone id(s): {named}" + (f" (+{more} more)" if more > 0 else "")
        return (head + tail)[:MAX_LINE_CHARS]


@dataclass(frozen=True)
class NobleRoomRead:
    #: Every unmet (position, holder, kind), covered or not.
    items: Tuple[NobleRoomItem, ...] = ()
    #: Keys of positions that could not be judged this poll: their state is kept.
    unreadable: FrozenSet[str] = frozenset()
    #: Holder unit ids with an open assign-owner proposal or step (coverage).
    covered_units: FrozenSet[int] = frozenset()
    #: Position codes whose requirements read failed; their keys are kept.
    unreadable_codes: FrozenSet[str] = frozenset()

    @property
    def wakeable(self) -> Tuple[NobleRoomItem, ...]:
        return tuple(i for i in self.items if i.unit_id not in self.covered_units)


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def held_positions(result: Any, limit: int) -> Optional[List[Tuple[str, int, str]]]:
    """`(code, holder unit id, position name)` per held position from
    `nobles.list`, capped at `limit`; `None` when the result is not a position
    list (the poll failed). A code held in several slots appears once per holder."""
    if not isinstance(result, Mapping) or not isinstance(result.get("positions"), list):
        return None
    out: List[Tuple[str, int, str]] = []
    seen = set()
    for row in result["positions"]:
        if not isinstance(row, Mapping) or row.get("vacant") is not False:
            continue
        code, uid = row.get("code"), _int(row.get("holder_unit_id"))
        if not isinstance(code, str) or not code or uid is None or uid < 0:
            continue
        if (code, uid) in seen:
            continue
        seen.add((code, uid))
        out.append((code, uid, str(row.get("name") or "")))
        if len(out) >= limit:
            break
    return out


def unmet_kinds(result: Any, uid: int, statuses: Sequence[str]) -> Optional[List[str]]:
    """Room kinds a `nobles.requirements` result says holder `uid` needs and
    owns none of. `None` when the result is unreadable. An assignment of another
    holder is ignored (a code can have several slots)."""
    if not isinstance(result, Mapping) or not isinstance(result.get("assignments"), list):
        return None
    kinds: List[str] = []
    for row in result["assignments"]:
        if not isinstance(row, Mapping) or _int(row.get("holder_unit_id")) != uid:
            continue
        rv = row.get("room_value")
        if not isinstance(rv, Mapping):
            continue
        for kind, st in rv.items():
            if not isinstance(st, Mapping) or st.get("status") not in statuses:
                continue
            if st.get("zone_ids"):
                continue  # owns a zone of this kind: a furnishing matter, not ownership
            if kind not in kinds:
                kinds.append(str(kind))
    return kinds


def unowned_zone_ids(result: Any) -> Optional[Tuple[int, ...]]:
    """Zone ids from a filtered `zone.list`; `None` when unreadable."""
    if not isinstance(result, Mapping) or not isinstance(result.get("zones"), list):
        return None
    ids = [_int(z.get("id")) for z in result["zones"] if isinstance(z, Mapping)]
    return tuple(i for i in ids if i is not None)


def covered_unit_ids(overview: Any) -> Optional[FrozenSet[int]]:
    """Unit ids named by an open `zone.assign-owner` step, from `queue.overview`
    with `open_steps_for`. `None` when the overview does not carry the block."""
    if not isinstance(overview, Mapping) or not isinstance(overview.get("open_steps"), list):
        return None
    out = set()
    for row in overview["open_steps"]:
        if not isinstance(row, Mapping) or row.get("tool") != ASSIGN_TOOL:
            continue
        args = row.get("args")
        if isinstance(args, Mapping):
            uid = _int(next((v for k, v in args.items() if str(k).lower() == "unit_id"), None))
            if uid is not None:
                out.add(uid)
    return frozenset(out)
