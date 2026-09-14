"""Reading and (append-only) writing the proposal queue.

JSONL, one file per fort, same reasoning as `learning/predictions/store.py`
and `learning/ledger/store.py`: a full scan is instant at this scale, rows
diff individually in `git log`, and the file stays readable with `cat`. This
*is* the append-only, write-time-validated channel `docs/AGENT-ARCHITECTURE.md`
§4 specifies ("The queue is the channel and the audit log") and the
write-ahead log §9 describes.

One write path, deliberately: `append()`. Unlike `learning/predictions/`,
which has a second path (`rewrite_all`) for grading updates, nothing here
ever rewrites a record in place — a `ruling` is itself a new append that
refers back to the `proposal` it decides, not an edit of that proposal. That
is what makes "an unaudited communication is structurally impossible" (§4)
literally true of this file: nothing already written can change.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schema import PROPOSAL, RULING, fort_name, validate

DEFAULT_DIR = Path(__file__).resolve().parent


class QueueError(Exception):
    """Raised when a record would corrupt the queue. Never swallowed."""


def default_path(fort: str | None = None) -> Path:
    return DEFAULT_DIR / f"{fort or fort_name()}.jsonl"


def load(path: str | Path) -> list[dict]:
    """Load every record. Invalid rows raise rather than being skipped.

    Skipping a bad row would silently shrink the audit log without the
    shrinkage showing up anywhere — same reasoning as
    `learning.predictions.store.load` and `learning.ledger.store.load`.
    """
    p = Path(path)
    if not p.exists():
        return []

    records: list[dict] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QueueError(f"{p}:{lineno}: not valid JSON: {exc}") from exc
        errors = validate(record)
        if errors:
            raise QueueError(
                f"{p}:{lineno}: invalid queue record:\n  " + "\n  ".join(errors)
            )
        records.append(record)

    ids = [r["id"] for r in records]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise QueueError(f"{p}: duplicate id(s): {sorted(duplicates)}")

    return records


def _next_id(existing: list[dict], kind: str) -> str:
    n = sum(1 for r in existing if r.get("kind") == kind) + 1
    return f"{kind}-{n:04d}"


def append(record: dict, path: str | Path) -> dict:
    """Validate and append one record. Refuses a malformed record with
    every error listed, writing nothing. Returns the record as written
    (with `id`/`ts` filled in if they were absent).

    Two checks need the rest of the queue and so cannot live in
    `schema.validate()`, which is stateless per record:
    - a fresh record's `id` must not collide with one already in the file;
    - a `ruling`'s `proposal_id` must name a `proposal` already in the file.
    Both are checked here, against `existing`, before anything is written.
    """
    if not isinstance(record, dict):
        raise QueueError("refusing to append a malformed record:\n  record: expected an object")

    p = Path(path)
    existing = load(p)

    record = dict(record)  # never mutate the caller's dict
    if not record.get("id"):
        record["id"] = _next_id(existing, record.get("kind"))
    if not record.get("ts"):
        record["ts"] = datetime.now(timezone.utc).isoformat()

    errors = validate(record)

    existing_ids = {r["id"] for r in existing}
    if record["id"] in existing_ids:
        errors.append(f"record.id: {record['id']!r} is already in the queue")

    if record.get("kind") == RULING and not _proposal_id_already_flagged(errors):
        proposal_id = record.get("proposal_id")
        proposals = {r["id"] for r in existing if r.get("kind") == PROPOSAL}
        if proposal_id not in proposals:
            errors.append(
                f"record.proposal_id: {proposal_id!r} does not refer to an "
                "existing proposal in this queue"
            )

    if errors:
        raise QueueError("refusing to append an invalid record:\n  " + "\n  ".join(errors))

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

    return record


def _proposal_id_already_flagged(errors: list[str]) -> bool:
    """True if `schema.validate` already flagged `proposal_id` itself
    (missing/empty/wrong type) — in which case the dangling-reference check
    below would be checking a value already known to be junk."""
    return any(e.startswith("record.proposal_id:") for e in errors)
