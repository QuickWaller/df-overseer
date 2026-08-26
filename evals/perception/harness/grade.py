"""Mechanical grading. No model is ever asked to judge another model's answer.

That is deliberate and matches the register's standing position on grading
(decisions/DECISIONS.md, 2026-08-25: "All learning grading is mechanical").
An LLM judge here would be grading exactly the kind of spatial claim this
harness exists to establish LLMs are unreliable about.

Normalisation is generous about surface form and strict about content: case,
articles, trailing punctuation and compass spellings are forgiven; a different
landmark, number or direction is not. The point is to measure comprehension,
not format compliance — the model is already pinned to a JSON answer schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .fixture import ADJACENT, COMPASS
from .questions import UNKNOWN

_LONG_COMPASS = {
    "north": "N",
    "northeast": "NE",
    "north east": "NE",
    "north-east": "NE",
    "east": "E",
    "southeast": "SE",
    "south east": "SE",
    "south-east": "SE",
    "south": "S",
    "southwest": "SW",
    "south west": "SW",
    "south-west": "SW",
    "west": "W",
    "northwest": "NW",
    "north west": "NW",
    "north-west": "NW",
}


def norm(value: Any) -> str:
    s = str(value).strip().casefold()
    s = re.sub(r"[.,;:!?]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^the\s+", "", s)
    return s


def norm_compass(value: Any) -> str:
    s = norm(value)
    if s in _LONG_COMPASS:
        return _LONG_COMPASS[s]
    upper = s.upper().replace("-", "").replace(" ", "")
    return upper if upper in COMPASS else s


@dataclass
class Grade:
    correct: bool
    abstained: bool
    near_miss: bool
    note: str = ""


def _abstained(answer: Any) -> bool:
    if isinstance(answer, str):
        return norm(answer) == norm(UNKNOWN)
    if isinstance(answer, list):
        return len(answer) == 1 and norm(answer[0]) == norm(UNKNOWN)
    return False


def grade(kind: str, expected: Any, got: Any) -> Grade:
    if _abstained(got) and not _abstained(expected):
        return Grade(False, True, False, "abstained")

    if kind == "exact":
        return Grade(norm(expected) == norm(got), _abstained(expected) and _abstained(got), False)

    if kind == "compass":
        e, g = norm_compass(expected), norm_compass(got)
        if e == g:
            return Grade(True, False, False)
        return Grade(False, False, g in ADJACENT.get(e, set()), f"expected {e}, got {g}")

    if kind == "int_exact":
        try:
            return Grade(int(expected) == int(str(got).strip()), False, False)
        except (TypeError, ValueError):
            return Grade(False, False, False, f"unparseable integer: {got!r}")

    if kind == "bool":
        if isinstance(got, bool):
            return Grade(bool(expected) == got, False, False)
        truthy = {"true", "yes"}
        falsy = {"false", "no"}
        g = norm(got)
        if g in truthy or g in falsy:
            return Grade(bool(expected) == (g in truthy), False, False)
        return Grade(False, False, False, f"unparseable boolean: {got!r}")

    if kind == "set":
        if not isinstance(got, list):
            return Grade(False, False, False, f"expected a list, got {type(got).__name__}")
        e = {norm(x) for x in expected}
        g = {norm(x) for x in got}
        if e == g:
            return Grade(True, False, False)
        missing = sorted(e - g)
        extra = sorted(g - e)
        # A single wrong element is a different failure from a scrambled answer.
        near = len(missing) + len(extra) == 1
        return Grade(False, False, near, f"missing={missing} extra={extra}")

    if kind == "sequence":
        if not isinstance(got, list):
            return Grade(False, False, False, f"expected a list, got {type(got).__name__}")
        e = [norm(x) for x in expected]
        g = [norm(x) for x in got]
        if e == g:
            return Grade(True, False, False)
        # Right rooms, wrong order is worth distinguishing: it means the model
        # found the route and lost the sequencing, not that it got lost.
        return Grade(False, False, sorted(e) == sorted(g), f"expected {e}, got {g}")

    raise KeyError(f"unknown grader {kind!r}")


ANSWER_SCHEMA = {
    "string": {"type": "string"},
    "string_list": {"type": "array", "items": {"type": "string"}},
    "integer": {"type": "integer"},
    "boolean": {"type": "boolean"},
}


def response_schema(answer_type: str) -> dict:
    """The JSON shape the model must return.

    `confidence` is collected, never graded — it is there so the report can say
    whether wrong answers were also confident answers. An agent that knows when
    it does not know can call a zoom tool; one that does not, cannot.
    """
    return {
        "type": "object",
        "properties": {
            "answer": ANSWER_SCHEMA[answer_type],
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["answer", "confidence"],
        "additionalProperties": False,
    }
