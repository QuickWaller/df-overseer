"""Exposed ore: polled from `blueprint.sites`, because nothing emits an event.

handoffs/2026-10-05-ore-exposed-signal.md. A dig can uncover ore in the walls
of a room (live 2026-10-05: hematite in the corners of two bedrooms near
Activity Zone #5), and nothing told an agent. Each row of `blueprint.sites`
now carries `ore_exposed`: the ore or gem still walled in on the faces ringing
that site's room rectangle, read from `surface.vein-material`'s `exposed`
block. Only tiles a player can see are ever reported (hidden tiles are never
read), and a tile already mined open no longer counts, so mining the vein
clears the exposure.

This module only parses the poll into `OreExposure` records and one-line
descriptions. The edge-trigger rule (a vein wakes the Architect once until it
is mined or a renotify window passes) lives in `conductor/lanes.py`, with the
rest of the lane state, so it is data-driven from `policy.yaml`
(`lane_triggers.<role>.ore`, `ore_renotify_ticks`).

What the poll can and cannot say
--------------------------------
- A site whose row has no readable `ore_exposed` (null, an error, a `skipped`
  note because its template declares no room) is reported in
  `unreadable_handles`. The caller keeps that site's edge state rather than
  treating the silence as "mined".
- A whole poll that fails or returns something that is not a list is `None`,
  not an empty read: state is kept, never cleared.
- Sites only. Areas dug outside a blueprint site (a bare `diggable.dig`) have
  no room rectangle to read and are not polled; the Architect can read any
  zone on demand with `surface.vein-material`.

This module never designates, mines or proposes anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, List, Mapping, Optional, Tuple

#: Tool the conductor polls (agents/conductor/tools.yaml).
POLL_TOOL = "blueprint.sites"

#: Tool that mines a site's exposed ore; named in briefing lines only.
MINE_TOOL = "construction.mine-vein-site"

#: Briefing and wake lines are bounded like every other conductor line.
MAX_LINE_CHARS = 200


@dataclass(frozen=True)
class OreExposure:
    """One (site, material) with unmined ore or gem showing on its room's walls."""
    handle: str
    mineral: str
    kind: str
    tiles: int
    line: str

    @property
    def key(self) -> str:
        return f"{self.handle}:{self.mineral}"


@dataclass(frozen=True)
class OreRead:
    exposures: Tuple[OreExposure, ...] = ()
    #: Sites polled but not readable this time: their edge state is kept.
    unreadable_handles: FrozenSet[str] = frozenset()

    @property
    def lines(self) -> List[str]:
        return [e.line for e in self.exposures]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _where(row: Mapping) -> str:
    landmark = _text(row.get("near_landmark"))
    if not landmark:
        return ""
    dist = row.get("distance_tiles")
    direction = _text(row.get("direction"))
    offset = " ".join(p for p in (f"{dist} tiles" if dist is not None else "", direction) if p)
    return f" ({offset} of {landmark})" if offset else f" (near {landmark})"


def describe(row: Mapping, mineral: str, kind: str, tiles: int) -> str:
    """`HEMATITE ore: 2 tiles exposed on site-5's room walls (4 tiles N of Well); mine with construction.mine-vein-site site-5`."""
    handle = _text(row.get("handle"))
    noun = "tile" if tiles == 1 else "tiles"
    line = (
        f"{mineral} {kind or 'ore'}: {tiles} {noun} exposed on {handle}'s room walls"
        f"{_where(row)}; mine with {MINE_TOOL} {handle}"
    )
    return line[:MAX_LINE_CHARS]


def _materials(exposed: Mapping) -> List[Mapping]:
    mats = exposed.get("materials")
    if isinstance(mats, list):
        return [m for m in mats if isinstance(m, Mapping)]
    return []  # an empty Lua table may serialise as {} or []


def ore_read_from_sites(result: Any) -> Optional[OreRead]:
    """Parse `blueprint.sites` (a bare array, or a dict wrapper holding one).
    `None` when `result` is not a site list at all: a failed poll must never
    read as "no ore"."""
    rows = result
    if isinstance(result, Mapping):
        rows = next((result[k] for k in ("sites", "result") if isinstance(result.get(k), list)), None)
    if not isinstance(rows, list):
        return None

    exposures: List[OreExposure] = []
    unreadable: List[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        handle = _text(row.get("handle"))
        if not handle:
            continue
        exposed = row.get("ore_exposed")
        if not isinstance(exposed, Mapping) or exposed.get("unreadable") or exposed.get("error") or exposed.get("skipped"):
            unreadable.append(handle)
            continue
        for mat in _materials(exposed):
            mineral = _text(mat.get("mineral_name"))
            try:
                tiles = int(mat.get("tiles") or 0)
            except (TypeError, ValueError):
                tiles = 0
            if not mineral or tiles <= 0:
                continue
            kind = _text(mat.get("kind"))
            exposures.append(OreExposure(handle, mineral, kind, tiles, describe(row, mineral, kind, tiles)))
    exposures.sort(key=lambda e: (e.handle, e.mineral))
    return OreRead(tuple(exposures), frozenset(unreadable))
