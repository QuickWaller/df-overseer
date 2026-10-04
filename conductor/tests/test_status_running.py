"""conductor/status.py::status_running: the mid-run block dfqueue/live.py reads."""

from __future__ import annotations

from datetime import datetime, timezone

from conductor.status import status_running
from dfqueue import live


def test_status_running_block_shape():
    s = status_running("architect", "routine_review", started_at="2026-10-05T12:00:00+00:00")
    assert s["state"] == "running"
    assert s["running"] == {
        "role": "architect", "wake_reason": "routine_review", "started_at": "2026-10-05T12:00:00+00:00",
    }


def test_the_live_view_reads_the_block_it_defines():
    now = datetime(2026, 10, 5, 12, 1, 0, tzinfo=timezone.utc).timestamp()
    started = datetime.fromtimestamp(now - 30, timezone.utc).isoformat()
    block = status_running("architect", "ask_open", started_at=started)
    calls = [{"ts": now - 5, "role": "architect", "tool": "zone.list", "is_error": False}]
    out = live.build_live(calls, now, public=True, conductor={"running": block["running"], "last_runs": {}})
    assert out["awake"][0]["wake_reason"] == "ask_open"
