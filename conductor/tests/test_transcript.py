"""The full per-run transcript (conductor/runner.py build_transcript,
read_transcript, load_transcript_caps; handoffs/2026-10-07-transcripts-and-
full-proposals.md). The tool-call event shape is UNVERIFIED live."""
from __future__ import annotations

import json
import sqlite3

from conductor.runner import (
    DEFAULT_TRANSCRIPT_CAPS, build_transcript, load_transcript_caps, read_transcript,
)

EVENTS = [
    {"message": {"role": "user", "content": [{"type": "text", "text": "go"}]}},
    {"message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "Check food first."},
        {"type": "toolCall", "id": "c1", "name": "stocks.get", "arguments": {"kind": "drink"}}],
        "usage": {"input": 100, "output": 20, "cacheRead": 80, "totalTokens": 120, "junk": 1}}},
    {"message": {"role": "toolResult", "toolCallId": "c1", "content": [{"type": "text", "text": "drink: 12"}]}},
    {"message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}},
]


def test_rounds_calls_results_and_usage():
    t = build_transcript(EVENTS)
    assert t["omitted_rounds"] == 0 and len(t["rounds"]) == 2
    r1, r2 = t["rounds"]
    assert r1["reasoning"] == "Check food first."
    assert r1["calls"] == [{"id": "c1", "name": "stocks.get", "args": '{"kind": "drink"}',
                            "result": "drink: 12", "error": False}]
    assert r1["usage"] == {"input": 100, "output": 20, "cacheRead": 80, "total": 120}
    assert r2["text"] == "Done." and r2["calls"] == [] and r2["usage"] is None


def test_caps_apply_per_field_rounds_and_total():
    caps = {**DEFAULT_TRANSCRIPT_CAPS, "max_result_chars": 10, "max_call_args_chars": 8, "max_rounds": 2}
    ev = [
        {"message": {"role": "assistant", "content": [
            {"type": "toolUse", "id": "a", "name": "t", "input": {"long": "x" * 50}}]}},
        {"message": {"role": "toolResult", "toolCallId": "a", "content": "y" * 50, "isError": True}},
    ] + [{"message": {"role": "assistant", "content": [{"type": "text", "text": f"r{i}"}]}} for i in range(4)]
    t = build_transcript(ev, caps)
    c = t["rounds"][0]["calls"][0]
    assert len(c["args"]) <= 8 and len(c["result"]) <= 10 and c["error"] is True
    assert len(t["rounds"]) == 2 and t["omitted_rounds"] == 3
    small = {**DEFAULT_TRANSCRIPT_CAPS, "max_total_chars": 400, "max_round_text_chars": 100}
    big = [{"message": {"role": "assistant", "content": [{"type": "text", "text": "z" * 100}]}} for _ in range(10)]
    t2 = build_transcript(big, small)
    assert len(json.dumps(t2["rounds"])) <= 400 and t2["omitted_rounds"] > 0


def test_nothing_usable_is_none():
    assert build_transcript([{"other": 1}, {"message": {"role": "user", "content": "hi"}}]) is None


def test_read_transcript_from_state_dir_and_never_raises(tmp_path):
    db = tmp_path / "agents" / "x" / "agent" / "openclaw-agent.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE transcript_events (session_id TEXT, seq INTEGER, event_json TEXT)")
    for i, ev in enumerate(EVENTS):
        conn.execute("INSERT INTO transcript_events VALUES ('s', ?, ?)", (i, json.dumps(ev)))
    conn.commit()
    conn.close()
    assert len(read_transcript(tmp_path)["rounds"]) == 2
    assert read_transcript(tmp_path / "missing") is None
    db.write_text("not a db")
    assert read_transcript(tmp_path) is None


def test_caps_come_from_policy_yaml_and_fall_back(tmp_path):
    assert load_transcript_caps()["max_rounds"] == DEFAULT_TRANSCRIPT_CAPS["max_rounds"]
    p = tmp_path / "p.yaml"
    p.write_text("transcript:\n  max_rounds: 5\n  max_result_chars: bad\n")
    caps = load_transcript_caps(p)
    assert caps["max_rounds"] == 5 and caps["max_result_chars"] == DEFAULT_TRANSCRIPT_CAPS["max_result_chars"]
    assert load_transcript_caps(tmp_path / "none.yaml") == DEFAULT_TRANSCRIPT_CAPS


def test_the_archive_run_file_carries_the_transcript(tmp_path):
    from conductor.archive import CycleArchive
    from conductor.runner import RunResult
    t = build_transcript(EVENTS)
    run = RunResult(role="architect", ok=True, status="ok", cost_usd=None, wall_clock_seconds=1.0,
                    timed_out=False, tool_summary={}, final_answer=None, raw={}, transcript=t)
    d = CycleArchive(tmp_path).write_cycle(1, summary={}, briefings={}, clock_changes=[], role_runs=[run])
    assert json.loads((d / "run-architect.json").read_text(encoding="utf-8"))["transcript"] == t
