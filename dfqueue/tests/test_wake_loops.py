"""Loop and deliberation signals in wake_metrics (`loops` block, per-wake `loop`)."""

from __future__ import annotations

import json

from dfqueue import wake_metrics as wm
from dfqueue.tests.test_wake_metrics import (EPOCHS, allow, prop, run, tr, write_queue,
                                             write_runs)

AV = "df-quartermaster__stocks__availability"
OL = "df-quartermaster__orders__list"
PR = "df-quartermaster__queue__propose"


def metrics(t):
    return wm.transcript_metrics(json.dumps(t), "quartermaster", allow(), set())


def test_repeated_identical_calls_counted_with_worst_offender():
    t = tr([(AV, '{"type": "BARREL"}', False)],
           [(AV, '{"type":   "BARREL"}', False)],      # same canonical args
           [(AV, '{"type": "BARREL"}', False)],
           [(OL, "{}", False)],
           [(OL, "{}", False)],
           [(PR, '{"a": 1}', False)])
    lp = metrics(t)["loop"]
    assert lp["repeated_calls"] == 3                      # AV x3 -> 2, OL x2 -> 1
    assert (lp["worst_tool"], lp["worst_count"]) == ("stocks.availability", 3)
    assert lp["rereads"] == 3


def test_failed_and_clipped_calls_are_not_identity_keyed():
    t = tr([(PR, '{"summary": "' + "x" * 50 + "…", False)],      # clipped, unparsable
           [(PR, '{"summary": "' + "x" * 50 + "…", False)],
           [(OL, "{}", True)], [(OL, "{}", True)])                     # both failed
    lp = metrics(t)["loop"]
    assert lp["repeated_calls"] == 0 and lp["worst_tool"] is None and lp["worst_count"] == 0


def test_idle_rounds_are_read_only_rounds_with_no_write_after():
    t = tr([(AV, "{}", False)],                 # orientation, a write follows: not idle
           [(PR, "{}", False)],
           [(OL, '{"p": 1}', False)],           # idle
           [(OL, '{"p": 2}', False), (AV, "{}", False)],   # idle
           [])                                  # final answer round: not a read round
    lp = metrics(t)["loop"]
    assert lp["idle_rounds"] == 2
    t2 = tr([(AV, "{}", False)], [(OL, "{}", False)])      # never writes: all read rounds idle
    assert metrics(t2)["loop"]["idle_rounds"] == 2


def test_reasoning_tokens_per_run_and_per_round():
    t = tr([(AV, "{}", False)], [(PR, "{}", False)])
    t["rounds"][0]["usage"]["reasoningTokens"] = 100
    t["rounds"][1]["usage"]["reasoningTokens"] = 300
    t["rounds"][1]["reasoning"] = "abcd"
    lp = metrics(t)["loop"]
    assert lp["reasoning_tokens"] == 400 and lp["reasoning_per_round"] == 200.0
    assert lp["reasoning_max_round"] == 300 and lp["reasoning_chars"] == 4


def world(tmp_path):
    """A looping quartermaster wake, a clean one, and the planner run-0039
    shape: timeout, no records, no transcript."""
    looping = tr(*([[(AV, '{"type": "BARREL"}', False)]] * 4))        # 3 repeats, 4 idle rounds
    clean = tr([(AV, "{}", False)], [(PR, "{}", False)])
    recs = [prop(2, "2026-10-08T02:05:00+00:00")]
    runs = [run(1, "quartermaster", "2026-10-08T01:00:00+00:00", "2026-10-08T01:10:00+00:00", []),
            run(2, "quartermaster", "2026-10-08T02:00:00+00:00", "2026-10-08T02:10:00+00:00", ["proposal-0002"]),
            run(3, "planner", "2026-10-08T03:00:00+00:00", "2026-10-08T03:10:00+00:00", [],
                status="timeout", timed_out=0, cost_usd=0.047)]
    q, r = tmp_path / "q.sqlite3", tmp_path / "r.sqlite3"
    write_queue(q, recs, {})
    write_runs(r, runs, {"run-0001": looping, "run-0002": clean})
    return wm.compute(q, r, epochs=EPOCHS)


def test_report_flags_loop_and_planner_timeout_without_records(tmp_path):
    rep = world(tmp_path)
    assert rep["schema"] == "wake_metrics/1" and rep["minor"] >= 1
    lp = rep["loops"]
    flagged = {f["run_id"]: f for f in lp["flagged"]}
    assert set(flagged) == {"run-0001", "run-0003"}
    assert {"repeat_calls", "idle_rounds", "rereads"} <= set(flagged["run-0001"]["flags"])
    assert flagged["run-0001"]["worst_tool"] == "stocks.availability" and flagged["run-0001"]["worst_count"] == 4
    p = flagged["run-0003"]
    assert p["flags"] == ["no_output"] and p["timeout"] and p["no_output"]
    assert p["repeated_calls"] is None and p["reasoning_tokens"] is None     # no transcript: null, not zero
    q = lp["by_role"]["quartermaster"]
    assert q["wakes"] == 2 and q["with_transcript"] == 2 and q["flagged"] == 1
    assert q["repeated_calls"] == 3 and q["reasoning_tokens"] == 4 * 2 + 2 * 2
    assert lp["by_role"]["planner"]["timeouts"] == 1 and lp["by_role"]["planner"]["no_output"] == 1
    assert lp["by_role"]["planner"]["reasoning_per_run"] is None


def test_existing_consumers_keep_working_and_publish_stays_safe(tmp_path):
    rep = world(tmp_path)
    for key in ("totals", "by_role", "by_day", "wakes", "tool_usage", "notes"):
        assert key in rep
    row = next(w for w in rep["wakes"] if w["run_id"] == "run-0003")
    assert row["loop"]["no_output"] and row["loop"]["timeout"]
    text = json.dumps(rep["loops"])
    assert '{"type"' not in text                       # no arguments leak
    assert "Still" not in text
    out = wm.render_text(rep)
    assert "flagged run-0003 planner: no_output" in out
    json.dumps(rep)
