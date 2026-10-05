"""Reading a run's reasoning from openclaw's retained state dir
(conductor/runner.py read_thinking, cap_thinking;
handoffs/2026-10-05-agent-thinking.md findings)."""
from __future__ import annotations

import json
import sqlite3

from conductor.runner import THINKING_CUT_MARKER, THINKING_MAX_CHARS, cap_thinking, read_thinking


def _db(root, events):
    db = root / "agents" / "consultant" / "agent" / "openclaw-agent.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE transcript_events (session_id TEXT, seq INTEGER, event_json TEXT)")
    for i, ev in enumerate(events):
        conn.execute("INSERT INTO transcript_events VALUES (?, ?, ?)", ("s1", i, json.dumps(ev)))
    conn.commit()
    conn.close()


def test_reads_thinking_blocks_of_assistant_messages_in_order(tmp_path):
    _db(tmp_path, [
        {"message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "First, read the stocks."},
            {"type": "text", "text": "ok"}]}},
        {"message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "Then decide."}]}},
        {"other": "event"},
    ])
    assert read_thinking(tmp_path) == "First, read the stocks.\n\nThen decide."


def test_nothing_there_or_unreadable_is_none_never_an_error(tmp_path):
    assert read_thinking(tmp_path) is None
    bad = tmp_path / "agents" / "x" / "agent" / "openclaw-agent.sqlite"
    bad.parent.mkdir(parents=True)
    bad.write_text("not a database")
    assert read_thinking(tmp_path) is None


def test_cap_keeps_start_and_end():
    text = "A" * 9000 + "B" * 9000
    capped = cap_thinking(text)
    assert len(capped) <= THINKING_MAX_CHARS and THINKING_CUT_MARKER in capped
    assert capped.startswith("A") and capped.endswith("B")
    assert cap_thinking("short") == "short" and cap_thinking("") is None
