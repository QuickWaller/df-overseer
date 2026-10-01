"""`web/stream/fixtures/board-demo.jsonl` -- the stream board's hand-built
demo export (`handoffs/2026-10-02-stream-board.md`) -- must validate against
`dfqueue.schema.validate` record for record, now that the display fields
(`public_title`, `public_rationale`, `urgency`, step `label`, `hold_code`)
exist for real (`handoffs/2026-10-02-queue-display-fields.md`). The fixture
is plain JSONL, never run through `store.append` (no `records.jsonl`-shaped
file in this repo is -- see `dfqueue/tests/_helpers.py`'s own convention),
so this is the one place that would catch a tool id, outcome, or urgency
value drifting out of the real closed vocabularies the schema checks against
(`scripts/dfhack/TOOLS.yaml` via `dfmcp.registry`, `agents/ROSTER.yaml`,
`dfqueue/public_text.yaml`) as those vocabularies change in the future.
"""

from __future__ import annotations

import json
from pathlib import Path

from dfqueue import schema

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "web" / "stream" / "fixtures" / "board-demo.jsonl"
)


def _load_fixture_records() -> list[dict]:
    records = []
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def test_fixture_file_is_non_empty():
    records = _load_fixture_records()
    assert len(records) > 0


def test_every_fixture_record_validates_clean():
    records = _load_fixture_records()
    failures = []
    for record in records:
        errors = schema.validate(record)
        if errors:
            failures.append((record.get("id", "<no id>"), errors))
    assert failures == [], (
        "the following board-demo.jsonl records fail dfqueue.schema.validate:\n"
        + "\n".join(f"  {rid}: {errs}" for rid, errs in failures)
    )


def test_fixture_covers_every_board_state_the_handoff_names():
    """A cheap content guard, not a schema check: the handoff
    (`handoffs/2026-10-02-stream-board.md` plan item 3) asks this fixture to
    cover a done project, an active one with a held step, a waiting/ready
    chain, an amended plan with an added step, and a turned-down proposal --
    if a future edit strips one of these while keeping the file schema-valid,
    this still catches it."""
    records = _load_fixture_records()
    kinds = [r.get("kind") for r in records]
    assert kinds.count("project") >= 1
    assert kinds.count("amend") >= 1
    assert any(r.get("kind") == "ruling" and r.get("decision") == "reject" for r in records)
    assert any(
        r.get("kind") == "observation"
        and any(res.get("hold_code") for res in r.get("results", []))
        for r in records
    )
