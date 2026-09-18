"""Validator for `doctrine/seed.yaml`'s entry format.

The format is fully specified in the header comment of `doctrine/seed.yaml`;
this module enforces exactly that spec, nothing more. It is the first thing
that reads `doctrine/` at all -- no agent or tool does yet (see that header
and `docs/MEMORY-ARCHITECTURE.md`) -- so this validator's job is to keep the
data well-formed for whenever something does, and to run under the ambient
`python -m pytest` per `CLAUDE.md`'s "Traps before running anything".

Run as a script: `python -m doctrine.validate [path]` (defaults to
`doctrine/seed.yaml` next to this file). Prints every error and exits 1 if
any entry is invalid, exits 0 and prints "ok" otherwise.

Import `validate` for in-process use. It takes either a path (`str` or
`Path`) or already-parsed data (the list `yaml.safe_load` returns for
`seed.yaml`) and returns a list of error strings; an empty list means the
data is valid.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# The install this repo automates (DFHack 53.16-r1.1), and the only version a
# `verified` entry may cite as its confirming source (seed.yaml header,
# "Rule"). One module-level constant so the version lives in exactly one
# place.
INSTALL_VERSION = "53.16"

DEFAULT_PATH = Path(__file__).resolve().parent / "seed.yaml"

SCOPES = {"universal", "world", "site"}
STATUSES = {"prior", "verified", "refuted"}
TOPICS = {
    "food",
    "drink",
    "water",
    "farming",
    "seeds",
    "fishing",
    "labor",
    "health",
    "material",
}
SOURCE_KINDS = {
    "live-read",
    "game-data",
    "devlog",
    "bugtracker",
    "wiki",
    "forum",
    "user",
    "research",
}
READ_VALUES = {"opened", "search-summary", "recalled", "unrecorded"}

# `verified` requires at least one source of one of these kinds, describing
# INSTALL_VERSION exactly (seed.yaml header: "verified needs at least one
# live-read or game-data source that describes 53.16. Wiki, forum and user
# sources can make a prior, never a verification").
VERIFYING_KINDS = {"live-read", "game-data"}

ENTRY_REQUIRED = {"id", "scope", "status", "topics", "sources", "statement"}
ENTRY_OPTIONAL = {"note"}
ENTRY_ALLOWED = ENTRY_REQUIRED | ENTRY_OPTIONAL

SOURCE_REQUIRED = {"kind", "ref", "describes", "read"}
SOURCE_OPTIONAL = {"accessed"}
SOURCE_ALLOWED = SOURCE_REQUIRED | SOURCE_OPTIONAL


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _entry_label(entry: Any, index: int) -> str:
    """An entry's id where it has a usable one, else its list position --
    so an entry broken enough to be missing its own id can still be found.
    """
    if isinstance(entry, dict):
        entry_id = entry.get("id")
        if _non_empty_str(entry_id):
            return entry_id
    return f"entry[{index}]"


def _validate_source(entry_label: str, index: int, source: Any) -> list[str]:
    prefix = f"{entry_label}.sources[{index}]"
    if not isinstance(source, dict):
        return [f"{prefix}: expected a mapping, got {type(source).__name__}"]

    errors = []

    for key in SOURCE_REQUIRED:
        if key not in source:
            errors.append(f"{prefix}.{key}: required field is missing")

    for key in source:
        if key not in SOURCE_ALLOWED:
            errors.append(f"{prefix}.{key}: unknown field")

    if "kind" in source and source["kind"] not in SOURCE_KINDS:
        errors.append(
            f"{prefix}.kind: {source['kind']!r} is not one of {sorted(SOURCE_KINDS)}"
        )

    for key in ("ref", "describes"):
        if key in source and not _non_empty_str(source[key]):
            errors.append(
                f"{prefix}.{key}: expected a non-empty string, got {source[key]!r}"
            )

    if "read" in source and source["read"] not in READ_VALUES:
        errors.append(
            f"{prefix}.read: {source['read']!r} is not one of {sorted(READ_VALUES)}"
        )

    if "accessed" in source:
        accessed = source["accessed"]
        # YAML parses an unquoted ISO date (most `accessed:` lines in
        # seed.yaml) into a datetime.date, not a str -- accept both.
        if isinstance(accessed, date):
            pass
        elif isinstance(accessed, str):
            try:
                date.fromisoformat(accessed)
            except ValueError:
                errors.append(f"{prefix}.accessed: {accessed!r} is not an ISO date")
        else:
            errors.append(f"{prefix}.accessed: {accessed!r} is not an ISO date")

    return errors


def _verifies_install(sources: Any) -> bool:
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, dict):
            continue
        if (
            source.get("kind") in VERIFYING_KINDS
            and source.get("describes") == INSTALL_VERSION
        ):
            return True
    return False


def _validate_entry(entry: Any, index: int, seen_ids: dict) -> list[str]:
    label = _entry_label(entry, index)
    if not isinstance(entry, dict):
        return [f"{label}: expected a mapping, got {type(entry).__name__}"]

    errors = []

    for key in ENTRY_REQUIRED:
        if key not in entry:
            errors.append(f"{label}.{key}: required field is missing")

    for key in entry:
        if key not in ENTRY_ALLOWED:
            errors.append(f"{label}.{key}: unknown field")

    if "id" in entry:
        entry_id = entry["id"]
        if not _non_empty_str(entry_id):
            errors.append(f"{label}.id: expected a non-empty string, got {entry_id!r}")
        elif entry_id in seen_ids:
            errors.append(
                f"{label}.id: duplicate id {entry_id!r} "
                f"(already used by entry[{seen_ids[entry_id]}])"
            )
        else:
            seen_ids[entry_id] = index

    if "scope" in entry and entry["scope"] not in SCOPES:
        errors.append(f"{label}.scope: {entry['scope']!r} is not one of {sorted(SCOPES)}")

    if "status" in entry and entry["status"] not in STATUSES:
        errors.append(
            f"{label}.status: {entry['status']!r} is not one of {sorted(STATUSES)}"
        )

    if "topics" in entry:
        topics = entry["topics"]
        if not isinstance(topics, list) or not topics:
            errors.append(f"{label}.topics: expected a non-empty list, got {topics!r}")
        else:
            for topic in topics:
                if topic not in TOPICS:
                    errors.append(
                        f"{label}.topics: {topic!r} is not one of {sorted(TOPICS)}"
                    )

    if "sources" in entry:
        sources = entry["sources"]
        if not isinstance(sources, list) or not sources:
            errors.append(f"{label}.sources: expected a non-empty list, got {sources!r}")
        else:
            for source_index, source in enumerate(sources):
                errors.extend(_validate_source(label, source_index, source))

    if "statement" in entry and not _non_empty_str(entry["statement"]):
        errors.append(
            f"{label}.statement: expected a non-empty string, got {entry['statement']!r}"
        )

    if entry.get("status") == "verified" and not _verifies_install(entry.get("sources")):
        errors.append(
            f"{label}: status is 'verified' but no source has kind in "
            f"{sorted(VERIFYING_KINDS)} describing {INSTALL_VERSION!r}"
        )

    return errors


def validate(source: Any) -> list[str]:
    """Validate doctrine seed data.

    `source` is either a path to a YAML file (`str` or `Path`) or
    already-parsed data (a list of entry mappings, as `yaml.safe_load`
    returns for `seed.yaml`). Returns a list of error strings; an empty list
    means the data is valid.
    """
    if isinstance(source, (str, Path)):
        with open(source, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    else:
        data = source

    if data is None:
        return []

    if not isinstance(data, list):
        return [f"top level: expected a list of entries, got {type(data).__name__}"]

    errors: list[str] = []
    seen_ids: dict = {}
    for index, entry in enumerate(data):
        errors.extend(_validate_entry(entry, index, seen_ids))
    return errors


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else DEFAULT_PATH
    errors = validate(path)
    if errors:
        print(f"{path}: {len(errors)} error(s)")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"{path}: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
