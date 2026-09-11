"""Reading, writing and grading the prediction log.

JSONL, git-tracked, one row per prediction — the same reasoning as
`ledger/store.py`: a full scan is instant at this scale, rows diff
individually in `git log`, and the file stays readable with `cat`.

Two write paths, deliberately different:

- `register()` is **append-only** and is the pre-registration gate: a
  prediction must already be valid (including the falsifiability check in
  `schema.validate`) and must not already carry a grade. This is what makes
  "registered before the outcome was known" a checkable fact rather than a
  claim — the file's own append order plus `registered_at` is the record.
- `rewrite_all()` is how grading updates existing rows in place
  (`status`/`graded_at`/`actual_value`) — an edit, not an append, so it goes
  through the whole file rather than pretending a grade is a new event.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import PENDING, validate

DEFAULT_PATH = Path(__file__).resolve().parent / "predictions.jsonl"


class PredictionError(Exception):
    """Raised when a prediction row would corrupt the log. Never swallowed."""


def load(path: str | Path = DEFAULT_PATH) -> list[dict]:
    """Load every row. Invalid rows raise rather than being skipped.

    Skipping a bad row would silently shrink an already tiny sample without
    the shrinkage showing up in any count — same reasoning as
    `ledger.store.load`.
    """
    p = Path(path)
    if not p.exists():
        return []

    rows: list[dict] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PredictionError(f"{p}:{lineno}: not valid JSON: {exc}") from exc
        errors = validate(row)
        if errors:
            raise PredictionError(
                f"{p}:{lineno}: invalid prediction row:\n  " + "\n  ".join(errors)
            )
        rows.append(row)

    ids = [r["prediction_id"] for r in rows]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise PredictionError(f"{p}: duplicate prediction_id(s): {sorted(duplicates)}")

    return rows


def register(row: dict, path: str | Path = DEFAULT_PATH) -> None:
    """Validate and append one freshly-made prediction.

    Refuses anything that isn't a clean, ungraded, pending row — a prediction
    is registered once, before the outcome is known; correcting one later is
    grading (`rewrite_all`), never a second `register` call.
    """
    if row.get("status") != PENDING:
        raise PredictionError("a newly registered prediction must have status='pending'")
    if row.get("graded_at") is not None or row.get("actual_value") is not None:
        raise PredictionError("a newly registered prediction must not already carry a grade")

    errors = validate(row)
    if errors:
        raise PredictionError("refusing to register an invalid prediction:\n  " + "\n  ".join(errors))

    p = Path(path)
    existing = {r["prediction_id"] for r in load(p)}
    if row["prediction_id"] in existing:
        raise PredictionError(f"prediction_id {row['prediction_id']!r} is already registered")

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def rewrite_all(rows: list[dict], path: str | Path = DEFAULT_PATH) -> None:
    """Overwrite the whole log with `rows` — how a grading pass persists."""
    for row in rows:
        errors = validate(row)
        if errors:
            raise PredictionError("refusing to write an invalid prediction:\n  " + "\n  ".join(errors))

    ids = [r["prediction_id"] for r in rows]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise PredictionError(f"duplicate prediction_id(s): {sorted(duplicates)}")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
