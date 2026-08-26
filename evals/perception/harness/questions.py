"""Question generation, with ground truth computed from the fixture.

No expected answer is ever written by hand. Every question is produced by a
generator that reads the fixture and derives the answer from it, so editing a
fixture cannot leave a stale answer behind, and a question can never encode a
belief about the fortress that the fixture does not actually support.

Generators also refuse to emit ambiguous questions — a bearing that sits on an
octant boundary, a shortest route that has a tie, a "nearest" with two equal
candidates. An eval that grades an ambiguous question is measuring the grader's
opinion, not the model.

Each question declares `needs`: the classes of fact required to answer it. The
runner uses that against each representation's `provides` (see
representations.py) so a representation is never scored on a question its
encoding could not have contained the answer to.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, asdict
from typing import Any, Callable

from .fixture import COMPASS, Fixture

# The literal a model must return when the briefing does not contain the
# answer. Graded as an abstention, not a wrong answer — the two mean very
# different things for an agent that can call a zoom tool.
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Question:
    qid: str
    fixture_id: str
    category: str
    prompt: str
    answer: Any
    answer_type: str  # string | string_list | integer | boolean
    grader: str
    needs: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _rng(fixture: Fixture, category: str) -> random.Random:
    """Stable per-(fixture, category) sampling, so the question set is fixed."""
    return random.Random(f"{fixture.fixture_id}/{category}")


def _pick(rng: random.Random, items: list, n: int) -> list:
    items = sorted(items, key=repr)
    return items if len(items) <= n else rng.sample(items, n)


def _balanced(rng: random.Random, items: list, n: int, key) -> list:
    """Sample n items, spreading them across the distinct answers `key` gives.

    Guards against the failure where a category's questions nearly all share
    one answer, which a model passes by always giving that answer and learns
    nothing about.
    """
    buckets: dict = {}
    for item in sorted(items, key=repr):
        buckets.setdefault(key(item), []).append(item)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    out: list = []
    while len(out) < n and any(buckets.values()):
        for answer in sorted(buckets, key=repr):
            if buckets[answer] and len(out) < n:
                out.append(buckets[answer].pop())
    return out


Generator = Callable[[Fixture, int], list[Question]]
GENERATORS: dict[str, Generator] = {}


def generator(category: str, *needs: str):
    def wrap(fn):
        def inner(fx: Fixture, n: int) -> list[Question]:
            out = []
            for i, (prompt, answer, answer_type, grader) in enumerate(fn(fx, n)):
                out.append(
                    Question(
                        qid=f"{fx.fixture_id}:{category}:{i}",
                        fixture_id=fx.fixture_id,
                        category=category,
                        prompt=prompt,
                        answer=answer,
                        answer_type=answer_type,
                        grader=grader,
                        needs=tuple(sorted(needs)),
                    )
                )
            return out

        GENERATORS[category] = inner
        return inner

    return wrap


# --------------------------------------------------------------------------
# Geometry between directly connected landmarks — a reading test
# --------------------------------------------------------------------------


@generator("bearing", "connected_geometry")
def _bearing(fx: Fixture, n: int):
    rng = _rng(fx, "bearing")
    pairs = [p for p in fx.connected_pairs()]
    # Ask in both directions: a model that reads the exit list off one landmark
    # but cannot invert it fails only the reversed half.
    ordered = [(a, b) for a, b in pairs] + [(b, a) for a, b in pairs]
    for a, b in _balanced(rng, ordered, n, lambda p: fx.bearing(*p)):
        yield (
            f"In which compass direction does {b} lie from {a}? "
            f"Answer with one of: {', '.join(COMPASS)}.",
            fx.bearing(a, b),
            "string",
            "compass",
        )


@generator("bearing_far", "global_geometry")
def _bearing_far(fx: Fixture, n: int):
    rng = _rng(fx, "bearing_far")
    cands = [
        (a, b)
        for a, b in itertools.permutations(fx.names, 2)
        if fx.connection(a, b) is None and fx.bearing_is_unambiguous(a, b)
    ]
    for a, b in _balanced(rng, cands, n, lambda p: fx.bearing(*p)):
        yield (
            f"In which compass direction does {b} lie from {a}? "
            f"Answer with one of: {', '.join(COMPASS)}.",
            fx.bearing(a, b),
            "string",
            "compass",
        )


@generator("distance", "connected_geometry")
def _distance(fx: Fixture, n: int):
    rng = _rng(fx, "distance")
    for a, b in _pick(rng, fx.connected_pairs(), n):
        yield (
            f"In a straight line, how many tiles apart are {a} and {b}? "
            f"Answer with a whole number of tiles.",
            fx.straight_line_tiles(a, b),
            "integer",
            "int_exact",
        )


@generator("walk_distance", "connected_geometry")
def _walk_distance(fx: Fixture, n: int):
    rng = _rng(fx, "walk_distance")
    for a, b in _pick(rng, fx.connected_pairs(), n):
        conn = fx.connection(a, b)
        assert conn is not None
        yield (
            f"How many tiles does a dwarf actually walk to get from {a} to {b} "
            f"along the direct route between them?",
            conn.walk_tiles,
            "integer",
            "int_exact",
        )


@generator("zlevel", "connected_geometry")
def _zlevel(fx: Fixture, n: int):
    rng = _rng(fx, "zlevel")
    pairs = fx.connected_pairs()
    ordered = [(a, b) for a, b in pairs] + [(b, a) for a, b in pairs]
    # Most connected pairs share a level, so uniform sampling asks "same?" over
    # and over — which a model passes by always saying "same". Draw round-robin
    # from the three answers instead.
    for a, b in _balanced(rng, ordered, n, lambda p: fx.z_relation(*p)):
        yield (
            f"Is {b} above, below, or on the same z-level as {a}? "
            f"Answer with exactly one of: above, below, same.",
            fx.z_relation(a, b),
            "string",
            "exact",
        )


@generator("zlevel_far", "global_geometry")
def _zlevel_far(fx: Fixture, n: int):
    rng = _rng(fx, "zlevel_far")
    cands = [
        (a, b) for a, b in itertools.permutations(fx.names, 2) if fx.connection(a, b) is None
    ]
    for a, b in _balanced(rng, cands, n, lambda p: fx.z_relation(*p)):
        yield (
            f"Is {b} above, below, or on the same z-level as {a}? "
            f"Answer with exactly one of: above, below, same.",
            fx.z_relation(a, b),
            "string",
            "exact",
        )


@generator("nearest_connected", "connected_geometry")
def _nearest_connected(fx: Fixture, n: int):
    rng = _rng(fx, "nearest_connected")
    cands = []
    for name in fx.names:
        nbrs = fx.neighbours(name)
        if len(nbrs) < 2:
            continue
        dists = sorted((fx.straight_line_tiles(name, o), o) for o in nbrs)
        if dists[0][0] == dists[1][0]:
            continue  # tie: not a fair question
        cands.append((name, dists[0][1]))
    for name, nearest in _pick(rng, cands, n):
        yield (
            f"Of the landmarks directly connected to {name}, which one is the "
            f"shortest straight-line distance away? Answer with its name.",
            nearest,
            "string",
            "exact",
        )


# --------------------------------------------------------------------------
# Topology — the part a rendered map is supposed to be good at
# --------------------------------------------------------------------------


@generator("adjacency", "topology")
def _adjacency(fx: Fixture, n: int):
    rng = _rng(fx, "adjacency")
    cands = [name for name in fx.names if fx.neighbours(name)]
    for name in _pick(rng, cands, n):
        yield (
            f"Which landmarks connect directly to {name}? List every one, and "
            f"only those with a direct connection.",
            fx.neighbours(name),
            "string_list",
            "set",
        )


@generator("hops", "topology")
def _hops(fx: Fixture, n: int):
    rng = _rng(fx, "hops")
    cands = []
    for a, b in itertools.combinations(fx.names, 2):
        h = fx.hops(a, b)
        if h is not None and h >= 2:
            cands.append((a, b, h))
    for a, b, h in _pick(rng, cands, n):
        yield (
            f"Travelling only along direct connections, what is the fewest "
            f"number of connections needed to get from {a} to {b}?",
            h,
            "integer",
            "int_exact",
        )


@generator("route", "topology")
def _route(fx: Fixture, n: int):
    rng = _rng(fx, "route")
    cands = []
    for a, b in itertools.combinations(fx.names, 2):
        h = fx.hops(a, b)
        if h is not None and h >= 2 and fx.route_count(a, b) == 1:
            cands.append((a, b))
    for a, b in _pick(rng, cands, n):
        route = fx.shortest_route(a, b)
        yield (
            f"List, in order, the landmarks along the shortest route from {a} "
            f"to {b}, starting with {a} and ending with {b}.",
            route,
            "string_list",
            "sequence",
        )


@generator("reachability", "topology")
def _reachability(fx: Fixture, n: int):
    rng = _rng(fx, "reachability")
    pairs = list(itertools.combinations(fx.names, 2))
    # Balanced deliberately: an all-"yes" set is passed by a model that always
    # says yes. On a fully-connected fixture there is no "no" to draw, and the
    # category simply reports that.
    for a, b in _balanced(rng, pairs, n, lambda p: fx.hops(*p) is not None):
        yield (
            f"Can a dwarf walk from {a} to {b} using only the connections in "
            f"this briefing? Answer true or false.",
            fx.hops(a, b) is not None,
            "boolean",
            "bool",
        )


@generator("stranded", "topology", "facts")
def _stranded(fx: Fixture, n: int):
    if not fx.units:
        return
    yield (
        "Which of the citizens listed in this briefing are cut off from the "
        "main body of the fortress — that is, standing somewhere with no route "
        "to where most of the fortress is? List their names, or answer with an "
        "empty list if none are.",
        fx.stranded_units(),
        "string_list",
        "set",
    )


# --------------------------------------------------------------------------
# Facts, absence, and the hallucination probe
# --------------------------------------------------------------------------


@generator("count_kind", "facts")
def _count_kind(fx: Fixture, n: int):
    rng = _rng(fx, "count_kind")
    for kind in _pick(rng, sorted(fx.kinds()), n):
        yield (
            f"How many landmarks in this fortress are of kind {kind!r}?",
            len(fx.of_kind(kind)),
            "integer",
            "int_exact",
        )


@generator("kind_present", "facts")
def _kind_present(fx: Fixture, n: int):
    rng = _rng(fx, "kind_present")
    absent = ["hospital", "magma forge", "prison", "temple", "well", "tomb"]
    present = sorted(fx.kinds())
    half = max(1, n // 2)
    asked = [(k, True) for k in _pick(rng, present, n - half)] + [
        (k, False) for k in _pick(rng, [k for k in absent if k not in fx.kinds()], half)
    ]
    for kind, truth in asked:
        yield (
            f"Does this fortress have at least one landmark of kind {kind!r}? "
            f"Answer true or false.",
            truth,
            "boolean",
            "bool",
        )


@generator("absent_landmark", "facts")
def _absent_landmark(fx: Fixture, n: int):
    """The hallucination probe: ask about a place that does not exist.

    A model that invents a bearing here would, in the real system, invent a
    reason to send dwarves somewhere that is not there. Correct behaviour is
    the abstention literal.
    """
    rng = _rng(fx, "absent_landmark")
    # These must not name a landmark in ANY fixture — selftest.py enforces it,
    # because a name borrowed from a neighbouring fixture would quietly turn a
    # hallucination probe into a plausible-sounding real place.
    invented = [
        "the Copper Vault",
        "the Salt Cellar",
        "the Weaponsmith's Gallery",
        "the Outer Barbican",
    ]
    anchors = _pick(rng, fx.names, n)
    for i, anchor in enumerate(anchors):
        place = invented[i % len(invented)]
        yield (
            f"In which compass direction does {place} lie from {anchor}? "
            f"Answer with one of: {', '.join(COMPASS)}, or with the single "
            f"word {UNKNOWN} if the briefing does not say.",
            UNKNOWN,
            "string",
            "exact",
        )


# --------------------------------------------------------------------------


def build(fx: Fixture, per_category: int = 3, categories: list[str] | None = None) -> list[Question]:
    wanted = categories or sorted(GENERATORS)
    out: list[Question] = []
    for cat in wanted:
        if cat not in GENERATORS:
            raise KeyError(f"unknown category {cat!r}; known: {sorted(GENERATORS)}")
        out.extend(GENERATORS[cat](fx, per_category))
    return out
