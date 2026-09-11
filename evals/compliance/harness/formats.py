"""Doctrine renderers: the same rule set, in different surface forms.

Mirrors "Prompt Design at Scale"'s finding that format barely moves the
collapse point — tested here rather than assumed, against this project's own
model. `markdown` is the format this project's actual doctrine documents
(`docs/MEMORY-ARCHITECTURE.md`) already use.
"""

from __future__ import annotations

from typing import Callable

from .rules import Rule

Renderer = Callable[[list[Rule]], str]


def markdown(rules: list[Rule]) -> str:
    return "\n".join(f"- {r.text}" for r in rules)


def plain(rules: list[Rule]) -> str:
    return "\n".join(f"{i + 1}) {r.text}" for i, r in enumerate(rules))


def prose(rules: list[Rule]) -> str:
    return " ".join(r.text for r in rules)


FORMATS: dict[str, Renderer] = {
    "markdown": markdown,
    "plain": plain,
    "prose": prose,
}
