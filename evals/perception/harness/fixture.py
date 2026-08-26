"""Fixture loading, validation, and the geometry/topology ground truth.

A fixture is a hand-authored fortress: landmarks with true positions, the
walkable connections between them, and the fortress facts (population,
resources, units, alerts, events). Everything the harness asserts as a correct
answer is *computed from the fixture here* — nothing is hand-typed twice, so a
fixture edit can never leave a stale expected answer behind.

Coordinate convention (DF's): +x is east, +y is SOUTH, +z is up. North is -y.
Compass bearings are horizontal only; z is reported separately, because
stacked-on-different-floors is the case the design flags as its weakest point
(research/2026-08-25-spatial-perception.md, section 11).
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

# Index 0 is east, then counter-clockwise in 45-degree steps.
COMPASS = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]

# Two bearings are "adjacent" if they are one octant apart. Graded wrong, but
# tracked separately: a near-miss and a wild miss are different failures.
ADJACENT = {
    d: {COMPASS[(i - 1) % 8], COMPASS[(i + 1) % 8]} for i, d in enumerate(COMPASS)
}


@dataclass(frozen=True)
class Landmark:
    name: str
    kind: str
    pos: tuple[int, int, int]


@dataclass(frozen=True)
class Connection:
    a: str
    b: str
    via: str
    walk_tiles: int


@dataclass
class Fixture:
    fixture_id: str
    description: str
    fortress: str
    embark_biome: str
    in_game_date: str
    population: int
    landmarks: list[Landmark]
    connections: list[Connection]
    resources: dict
    units: list[dict]
    alerts: list[dict]
    events: list[dict]

    _by_name: dict[str, Landmark] = field(default_factory=dict, repr=False)
    _adj: dict[str, list[Connection]] = field(default_factory=dict, repr=False)

    # ---- construction ---------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "Fixture":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        t0 = raw["tier0"]
        fx = cls(
            fixture_id=raw["fixture_id"],
            description=raw.get("description", ""),
            fortress=t0["fortress"],
            embark_biome=t0["embark_biome"],
            in_game_date=t0["in_game_date"],
            population=t0["population"],
            landmarks=[
                Landmark(l["name"], l["kind"], tuple(l["pos"])) for l in raw["landmarks"]
            ],
            connections=[
                Connection(c["a"], c["b"], c.get("via", "corridor"), int(c["walk_tiles"]))
                for c in raw["connections"]
            ],
            resources=raw.get("resources", {}),
            units=raw.get("units", []),
            alerts=raw.get("alerts", []),
            events=raw.get("events", []),
        )
        fx._index()
        fx.validate()
        return fx

    def _index(self) -> None:
        self._by_name = {l.name: l for l in self.landmarks}
        self._adj = {l.name: [] for l in self.landmarks}
        for c in self.connections:
            self._adj[c.a].append(c)
            self._adj[c.b].append(c)

    def validate(self) -> None:
        """Fail loudly on anything that would make a graded answer meaningless."""
        names = [l.name for l in self.landmarks]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.fixture_id}: duplicate landmark names")
        for c in self.connections:
            for end in (c.a, c.b):
                if end not in self._by_name:
                    raise ValueError(
                        f"{self.fixture_id}: connection to unknown landmark {end!r}"
                    )
            if c.a == c.b:
                raise ValueError(f"{self.fixture_id}: self-connection on {c.a!r}")
        for u in self.units:
            if u.get("at") and u["at"] not in self._by_name:
                raise ValueError(
                    f"{self.fixture_id}: unit at unknown landmark {u['at']!r}"
                )
        # Two landmarks sharing a position make every bearing question ambiguous.
        seen: dict[tuple[int, int, int], str] = {}
        for l in self.landmarks:
            if l.pos in seen:
                raise ValueError(
                    f"{self.fixture_id}: {l.name!r} and {seen[l.pos]!r} share position {l.pos}"
                )
            seen[l.pos] = l.name
        # A bearing question is only fair if the pair is not near-degenerate:
        # check every connected pair lands cleanly inside one octant.
        for c in self.connections:
            if not self.bearing_is_unambiguous(c.a, c.b):
                raise ValueError(
                    f"{self.fixture_id}: bearing {c.a!r}->{c.b!r} sits on an octant "
                    "boundary; nudge a position so the compass answer is unambiguous"
                )

    # ---- lookups --------------------------------------------------------

    def landmark(self, name: str) -> Landmark:
        return self._by_name[name]

    @property
    def names(self) -> list[str]:
        return [l.name for l in self.landmarks]

    def neighbours(self, name: str) -> list[str]:
        return sorted(c.b if c.a == name else c.a for c in self._adj[name])

    def connection(self, a: str, b: str) -> Connection | None:
        for c in self._adj[a]:
            if {c.a, c.b} == {a, b}:
                return c
        return None

    def connected_pairs(self) -> list[tuple[str, str]]:
        return [(c.a, c.b) for c in self.connections]

    def kinds(self) -> set[str]:
        return {l.kind for l in self.landmarks}

    def of_kind(self, kind: str) -> list[str]:
        return sorted(l.name for l in self.landmarks if l.kind == kind)

    # ---- ground truth: geometry ----------------------------------------

    def bearing(self, frm: str, to: str) -> str:
        ax, ay, _ = self.landmark(frm).pos
        bx, by, _ = self.landmark(to).pos
        # -dy because +y is south; atan2 then measures a conventional bearing
        # with north up, which is the order the compass table above is in.
        deg = math.degrees(math.atan2(-(by - ay), bx - ax))
        return COMPASS[round(deg / 45) % 8]

    def bearing_is_unambiguous(self, frm: str, to: str, margin_deg: float = 10.0) -> bool:
        """True if the bearing sits at least `margin_deg` inside its octant.

        Octant boundaries fall every 45 degrees, offset by 22.5. The expression
        below is 22.5 at an octant's centre and 0 exactly on a boundary, so it
        reads directly as "degrees clear of the nearest boundary".
        """
        ax, ay, _ = self.landmark(frm).pos
        bx, by, _ = self.landmark(to).pos
        if (bx, by) == (ax, ay):
            return False  # directly above/below: no horizontal bearing exists
        deg = math.degrees(math.atan2(-(by - ay), bx - ax))
        clear_of_boundary = abs((deg % 45) - 22.5)
        return clear_of_boundary > margin_deg

    def straight_line_tiles(self, frm: str, to: str) -> int:
        ax, ay, _ = self.landmark(frm).pos
        bx, by, _ = self.landmark(to).pos
        return round(math.hypot(bx - ax, by - ay))

    def z_relation(self, frm: str, to: str) -> str:
        dz = self.landmark(to).pos[2] - self.landmark(frm).pos[2]
        return "above" if dz > 0 else "below" if dz < 0 else "same"

    def z_delta(self, frm: str, to: str) -> int:
        return self.landmark(to).pos[2] - self.landmark(frm).pos[2]

    # ---- ground truth: topology ----------------------------------------

    def shortest_route(self, frm: str, to: str) -> list[str] | None:
        """Fewest-connections route. Returns the landmark sequence, or None.

        The question generator only emits route questions where the shortest
        route is unique (see route_count), so BFS tie-breaking never decides a
        graded answer.
        """
        if frm == to:
            return [frm]
        prev: dict[str, str] = {frm: ""}
        q = deque([frm])
        while q:
            cur = q.popleft()
            for nxt in self.neighbours(cur):
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == to:
                        path = [to]
                        while path[-1] != frm:
                            path.append(prev[path[-1]])
                        return list(reversed(path))
                    q.append(nxt)
        return None

    def route_count(self, frm: str, to: str) -> int:
        """How many distinct shortest routes exist — used to reject ambiguity."""
        if frm == to:
            return 1
        dist = {frm: 0}
        ways = {frm: 1}
        q = deque([frm])
        order: list[str] = []
        while q:
            cur = q.popleft()
            order.append(cur)
            for nxt in self.neighbours(cur):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    ways[nxt] = 0
                    q.append(nxt)
        for cur in order:
            for nxt in self.neighbours(cur):
                if dist.get(nxt) == dist[cur] + 1:
                    ways[nxt] += ways[cur]
        return ways.get(to, 0)

    def hops(self, frm: str, to: str) -> int | None:
        route = self.shortest_route(frm, to)
        return None if route is None else len(route) - 1

    def component(self, name: str) -> frozenset[str]:
        seen = {name}
        q = deque([name])
        while q:
            for nxt in self.neighbours(q.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        return frozenset(seen)

    def components(self) -> list[frozenset[str]]:
        out: list[frozenset[str]] = []
        placed: set[str] = set()
        for name in self.names:
            if name not in placed:
                comp = self.component(name)
                placed |= comp
                out.append(comp)
        return out

    def main_component(self) -> frozenset[str]:
        return max(self.components(), key=lambda c: (len(c), sorted(c)[0]))

    def unit_is_stranded(self, unit: dict) -> bool:
        at = unit.get("at")
        return bool(at) and at not in self.main_component()

    def stranded_units(self) -> list[str]:
        return sorted(u["name"] for u in self.units if self.unit_is_stranded(u))


def load_all(directory: str | Path) -> list[Fixture]:
    return [Fixture.load(p) for p in sorted(Path(directory).glob("*.json"))]
