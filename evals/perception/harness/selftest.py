"""Checks on the harness itself. Run before trusting any result it produces.

    python -m evals.perception.harness.selftest

An eval is only as good as its ground truth, and every expected answer here is
produced by code that could be wrong in the same way twice. These checks are
deliberately independent of the generators: they re-derive answers a second way
(walking the graph, re-reading the fixture) rather than re-running the function
that produced them.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from .fixture import COMPASS, load_all
from .grade import grade
from .questions import GENERATORS, UNKNOWN, build
from .representations import REPRESENTATIONS

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

_TYPES = {"string": str, "string_list": list, "integer": int, "boolean": bool}

OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E", "NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW"}


def _raw_adjacency(fx) -> dict[str, set[str]]:
    """Neighbour map built straight from the fixture's connection list.

    Independent of Fixture.neighbours on purpose: a check that calls the same
    method the answer came from cannot detect that method being wrong.
    """
    adj: dict[str, set[str]] = {n: set() for n in fx.names}
    for c in fx.connections:
        adj[c.a].add(c.b)
        adj[c.b].add(c.a)
    return adj


def _raw_hops(fx, frm: str, to: str) -> int | None:
    adj = _raw_adjacency(fx)
    seen = {frm: 0}
    queue = [frm]
    while queue:
        cur = queue.pop(0)
        if cur == to:
            return seen[cur]
        for nxt in sorted(adj[cur]):
            if nxt not in seen:
                seen[nxt] = seen[cur] + 1
                queue.append(nxt)
    return None


def _bearing_agrees_with_coordinates(fx, frm: str, to: str, bearing: str) -> bool:
    """Sign test: each letter in a bearing makes a claim about one axis.

    Deliberately crude and deliberately not the bearing formula — it cannot
    tell NE from N, but it catches any bearing that points the wrong way, which
    is the failure that matters.
    """
    ax, ay, _ = fx.landmark(frm).pos
    bx, by, _ = fx.landmark(to).pos
    if "N" in bearing and not by < ay:
        return False
    if "S" in bearing and not by > ay:
        return False
    if "E" in bearing and not bx > ax:
        return False
    if "W" in bearing and not bx < ax:
        return False
    # A cardinal bearing claims the perpendicular axis is the minor one — not
    # that it is zero, since an octant is 45 degrees wide.
    if bearing in ("N", "S") and abs(bx - ax) >= abs(by - ay):
        return False
    if bearing in ("E", "W") and abs(by - ay) >= abs(bx - ax):
        return False
    return True


def _wrong_answer(q):
    """A definitely-incorrect answer of the right type, to prove graders bite."""
    if q.answer_type == "boolean":
        return not q.answer
    if q.answer_type == "integer":
        return q.answer + 7
    if q.answer_type == "string_list":
        return list(q.answer) + ["Nowhere At All"]
    return "Nowhere At All" if q.answer != "Nowhere At All" else "Somewhere Else"


def run() -> list[str]:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    fixtures = load_all(FIXTURE_DIR)
    check(len(fixtures) >= 2, "expected at least two fixtures")

    all_names = {n for fx in fixtures for n in fx.names}
    seen_qids: set[str] = set()
    categories_seen: set[str] = set()

    for fx in fixtures:
        questions = build(fx, per_category=4)
        check(bool(questions), f"{fx.fixture_id}: generated no questions")
        by_cat: dict[str, list] = {}
        for q in questions:
            by_cat.setdefault(q.category, []).append(q)
            categories_seen.add(q.category)

            check(q.qid not in seen_qids, f"duplicate qid {q.qid}")
            seen_qids.add(q.qid)

            # Answer matches its declared type.
            want = _TYPES[q.answer_type]
            check(
                isinstance(q.answer, want) and not (want is int and isinstance(q.answer, bool)),
                f"{q.qid}: answer {q.answer!r} is not {q.answer_type}",
            )

            # The grader accepts the truth and rejects a wrong answer. A grader
            # that accepts everything would make the whole eval read as a pass.
            check(grade(q.grader, q.answer, q.answer).correct, f"{q.qid}: grader rejects truth")
            check(
                not grade(q.grader, q.answer, _wrong_answer(q)).correct,
                f"{q.qid}: grader accepts a wrong answer",
            )

            # Some representation must be able to answer it at all.
            check(
                any(set(q.needs) <= r.provides for r in REPRESENTATIONS.values()),
                f"{q.qid}: needs {q.needs}, which no representation provides",
            )

            # Re-derive the answer independently of the generator.
            if q.category == "adjacency":
                anchor = q.prompt.split("connect directly to ")[1].split("?")[0]
                check(
                    set(q.answer) == _raw_adjacency(fx)[anchor],
                    f"{q.qid}: adjacency answer disagrees with the connection list",
                )
            if q.category == "route":
                route = q.answer
                adj = _raw_adjacency(fx)
                check(len(route) >= 3, f"{q.qid}: route too short to be a route question")
                for a, b in zip(route, route[1:]):
                    check(b in adj[a], f"{q.qid}: route step {a} -> {b} is not a connection")
                check(
                    len(route) - 1 == _raw_hops(fx, route[0], route[-1]),
                    f"{q.qid}: route is not a shortest route",
                )
                check(
                    fx.route_count(route[0], route[-1]) == 1,
                    f"{q.qid}: shortest route is not unique, so the answer is arbitrary",
                )
            if q.category == "hops":
                # Always parse the tail after "get from ", never the whole
                # prompt: the preamble contains its own " to " and splitting the
                # whole string silently compares the wrong pair of landmarks.
                frm, to = q.prompt.split("get from ")[1].rstrip("?").split(" to ", 1)
                check(
                    q.answer == _raw_hops(fx, frm, to),
                    f"{q.qid}: hop count disagrees with an independent walk",
                )
            if q.category in ("bearing", "bearing_far"):
                check(q.answer in COMPASS, f"{q.qid}: {q.answer!r} is not a compass point")
                frm = q.prompt.split(" lie from ")[1].split("?")[0]
                to = q.prompt.split("direction does ")[1].split(" lie from ")[0]
                check(
                    _bearing_agrees_with_coordinates(fx, frm, to, q.answer),
                    f"{q.qid}: bearing {q.answer} contradicts the coordinates "
                    f"({fx.landmark(frm).pos} -> {fx.landmark(to).pos})",
                )
                check(
                    fx.bearing(to, frm) == OPPOSITE[q.answer],
                    f"{q.qid}: bearing is not its own inverse when reversed",
                )
            if q.category == "distance":
                a, b = q.prompt.split("tiles apart are ")[1].split("?")[0].split(" and ")
                ax, ay, _ = fx.landmark(a).pos
                bx, by, _ = fx.landmark(b).pos
                check(
                    q.answer == round(math.hypot(bx - ax, by - ay)),
                    f"{q.qid}: {q.answer} tiles disagrees with the coordinates",
                )
            if q.category == "walk_distance":
                a, rest = q.prompt.split("get from ")[1].split(" to ", 1)
                b = rest.split(" along")[0]
                raw = [c for c in fx.connections if {c.a, c.b} == {a, b}]
                check(len(raw) == 1, f"{q.qid}: {a}/{b} is not exactly one connection")
                check(
                    bool(raw) and q.answer == raw[0].walk_tiles,
                    f"{q.qid}: walk distance disagrees with the connection list",
                )
            if q.category in ("zlevel", "zlevel_far"):
                to = q.prompt.split("Is ")[1].split(" above, below")[0]
                frm = q.prompt.split("z-level as ")[1].split("?")[0]
                az, bz = fx.landmark(frm).pos[2], fx.landmark(to).pos[2]
                expected = "above" if bz > az else "below" if bz < az else "same"
                check(
                    q.answer == expected,
                    f"{q.qid}: says {to} is {q.answer} {frm}, but z={bz} vs z={az}",
                )
            if q.category == "absent_landmark":
                check(q.answer == UNKNOWN, f"{q.qid}: probe should expect {UNKNOWN}")
                for line in [q.prompt]:
                    for name in all_names:
                        check(
                            f"does {name} lie" not in line,
                            f"{q.qid}: probe names a real landmark ({name})",
                        )
            if q.category == "stranded":
                main = fx.main_component()
                expected = sorted(
                    u["name"] for u in fx.units if u.get("at") and u["at"] not in main
                )
                check(
                    sorted(q.answer) == expected,
                    f"{q.qid}: stranded list disagrees with the component walk",
                )

        # Balanced categories should not be single-answer where the fixture has
        # more than one answer available.
        for cat in ("zlevel", "zlevel_far", "reachability"):
            qs = by_cat.get(cat, [])
            if len(qs) >= 2:
                available = {str(x.answer) for x in GENERATORS[cat](fx, 999)}
                got = {str(x.answer) for x in qs}
                check(
                    len(got) >= min(len(available), 2),
                    f"{fx.fixture_id}/{cat}: all sampled questions share one answer "
                    f"({got}) although {available} were available",
                )

    # A category that silently generates nothing is invisible in a results file:
    # it shows up as an absent row, not as a failure. Catch it here instead.
    missing = sorted(set(GENERATORS) - categories_seen)
    check(not missing, f"categories generated no questions on any fixture: {missing}")

    # Representations must be deterministic — the caching design depends on it.
    for name, rep in REPRESENTATIONS.items():
        for fx in fixtures:
            a, b = rep(fx), rep(fx)
            check(a == b, f"{name}/{fx.fixture_id}: representation is not byte-stable")
            check(bool(a.strip()), f"{name}/{fx.fixture_id}: empty briefing")
            # No representation may leak a rendered grid — commitment #1.
            check(
                "█" not in a and "###" not in a,
                f"{name}/{fx.fixture_id}: briefing looks like it contains a render",
            )

    failures.extend(_check_request_path())
    return failures


class _StubResponse:
    """Shaped like a Messages API response, enough for ask() to consume."""

    def __init__(self, payload: str):
        self.stop_reason = "end_turn"
        self.stop_details = None
        self.content = [type("Block", (), {"type": "text", "text": payload})()]
        self.usage = type(
            "Usage", (), {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 0}
        )()


class _StubClient:
    """Records the request instead of sending it."""

    def __init__(self, payload: str):
        self.payload = payload
        self.last: dict = {}
        self.messages = type("M", (), {"create": self._create})()

    def _create(self, **kwargs):
        self.last = kwargs
        return _StubResponse(self.payload)


def _check_request_path() -> list[str]:
    """Exercise ask() end to end against a stub.

    This cannot prove the request is accepted by the API — no credentials are
    needed to run the harness's offline paths, and none were used here. What it
    does prove is that the request assembles with the fields the run intends,
    and that a well-formed response is parsed and graded into a result row.
    """
    import json

    from .run import RULES, Cell, ask

    out: list[str] = []
    fx = load_all(FIXTURE_DIR)[0]
    q = next(x for x in build(fx, per_category=1) if x.answer_type == "string")
    cell = Cell(fx, "exits_v1", REPRESENTATIONS["exits_v1"](fx), q, 0)

    client = _StubClient(json.dumps({"answer": q.answer, "confidence": 0.9}))
    row = ask(client, "claude-opus-5", "medium", cell, 16000)
    sent = client.last

    if not row.get("correct"):
        out.append(f"request path: a correct answer graded as wrong ({row})")
    if row.get("error"):
        out.append(f"request path: unexpected error {row['error']}")
    if sent.get("model") != "claude-opus-5":
        out.append("request path: model not passed through")
    if sent.get("thinking") != {"type": "adaptive"}:
        out.append(f"request path: thinking is {sent.get('thinking')!r}, expected adaptive")
    if "budget_tokens" in json.dumps(sent):
        out.append("request path: budget_tokens is rejected by current models")
    fmt = (sent.get("output_config") or {}).get("format", {})
    if fmt.get("type") != "json_schema":
        out.append("request path: answers are not constrained to a JSON schema")
    system = sent.get("system") or []
    if (
        not isinstance(system, list)
        or len(system) != 2
        or not all(isinstance(b, dict) and "cache_control" in b for b in system)
    ):
        out.append(f"request path: the stable prefix is not marked cacheable ({system!r:.60})")
    elif system[0].get("text") != RULES:
        out.append("request path: the rules must precede the briefing for cache stability")

    # A malformed response must become an error row, not a silent pass.
    bad = ask(_StubClient("not json at all"), "claude-opus-5", "medium", cell, 16000)
    if not bad.get("error") or bad.get("correct"):
        out.append("request path: unparseable output was not recorded as an error")
    return out


def main() -> int:
    failures = run()
    if failures:
        print(f"{len(failures)} SELFTEST FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
