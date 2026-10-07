"""Tests for dfqueue/wake_metrics.py on fixture databases (no live data).

`fixtures/wake_window_2026_10_05.json` is the real 2026-10-05..07 window
(queue records, predictions, run rows, a trimmed transcript) with a
hand-labelled truth set; the validation test reports precision and recall
of each metric against it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from dfqueue import wake_metrics as wm

FIXTURE = Path(__file__).with_name("fixtures") / "wake_window_2026_10_05.json"
EPOCHS = [{"id": "e1", "since": "2026-10-05T00:00:00+00:00"}]


# ---- builders -------------------------------------------------------------

RUNS_SQL = """CREATE TABLE runs (run_id TEXT PRIMARY KEY, role TEXT NOT NULL, wake_reason TEXT,
 wake_detail TEXT, cycle INTEGER, started_at TEXT NOT NULL, ended_at TEXT, status TEXT, ok INTEGER,
 timed_out INTEGER, duration_s REAL, cost_usd REAL, records_json TEXT{extra})"""


def write_queue(path: Path, records: list, predictions: dict | None = None) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE records (id TEXT PRIMARY KEY, ts TEXT, kind TEXT, role TEXT, "
                 "cycle INTEGER, type TEXT, proposal_id TEXT, payload TEXT NOT NULL)")
    conn.execute("CREATE TABLE predictions (id INTEGER PRIMARY KEY, record_id TEXT, signal TEXT, "
                 "op TEXT, status TEXT)")
    for r in records:
        conn.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?)",
                     (r["id"], r["ts"], r["kind"], r["role"], r.get("cycle", 1), r.get("type"),
                      r.get("proposal_id"), json.dumps(r)))
    for rid, p in (predictions or {}).items():
        conn.execute("INSERT INTO predictions (record_id, signal, op, status) VALUES (?,?,?,?)",
                     (rid, p["signal"], p["op"], p["status"]))
    conn.commit()
    conn.close()


def write_runs(path: Path, runs: list, transcripts: dict | None = None, with_transcript_col: bool = True) -> None:
    conn = sqlite3.connect(path)
    conn.execute(RUNS_SQL.format(extra=", transcript TEXT" if with_transcript_col else ""))
    for r in runs:
        cols = ["run_id", "role", "wake_reason", "wake_detail", "cycle", "started_at", "ended_at",
                "status", "ok", "timed_out", "duration_s", "cost_usd", "records_json"]
        vals = [r.get(c) for c in cols]
        if with_transcript_col:
            cols.append("transcript")
            vals.append(json.dumps(transcripts[r["run_id"]]) if transcripts and r["run_id"] in transcripts else None)
        conn.execute(f"INSERT INTO runs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    conn.commit()
    conn.close()


def prop(i, ts, role="quartermaster", summary="Brew drink at the Still", rationale="drink is low", **kw):
    d = {"id": f"proposal-{i:04d}", "kind": "proposal", "ts": ts, "role": role, "type": "work_order",
         "summary": summary, "rationale": rationale}
    d.update(kw)
    return d


def ruling(i, ts, pid, decision, reason="ok"):
    return {"id": f"ruling-{i:04d}", "kind": "ruling", "ts": ts, "role": "overseer",
            "proposal_id": pid, "decision": decision, "reason": reason}


def run(i, role, start, end, ids, **kw):
    d = {"run_id": f"run-{i:04d}", "role": role, "wake_reason": "queue_pending", "cycle": i,
         "started_at": start, "ended_at": end, "status": "ok", "timed_out": 0, "cost_usd": 0.05,
         "records_json": json.dumps([{"id": x, "kind": x.split("-")[0], "thread": x} for x in ids])}
    d.update(kw)
    return d


def classify(records, predictions=None, runs=None):
    return wm.classify(records, predictions or {}, runs or [], [])


# ---- M1 / M3 / M2 cases ----------------------------------------------------


def test_repeat_after_rejection_is_m1():
    recs = [prop(1, "2026-10-05T01:00:00+00:00"), ruling(1, "2026-10-05T01:10:00+00:00", "proposal-0001", "reject"),
            prop(2, "2026-10-05T02:00:00+00:00")]
    c = classify(recs)
    assert c.m1 == {"proposal-0002": "proposal-0001"}
    assert c.m1_status["proposal-0002"] == "after_reject"


def test_parallel_serves_is_not_a_repeat():
    recs = [prop(1, "2026-10-05T01:00:00+00:00", serves=["plan-a"]),
            prop(2, "2026-10-05T02:00:00+00:00", serves=["plan-a"])]
    assert classify(recs).m1 == {}


def test_re_need_after_completed_is_not_a_repeat():
    recs = [prop(1, "2026-10-05T01:00:00+00:00"), ruling(1, "2026-10-05T01:10:00+00:00", "proposal-0001", "accept"),
            {"id": "close-0001", "kind": "close", "ts": "2026-10-05T01:30:00+00:00", "role": "conductor",
             "ruling_id": "ruling-0001", "outcome": "completed"},
            prop(2, "2026-10-05T02:00:00+00:00")]
    assert classify(recs).m1 == {}


def test_accepted_without_completion_is_a_repeat_executed_alone_is_not_completion():
    recs = [prop(1, "2026-10-05T01:00:00+00:00"), ruling(1, "2026-10-05T01:10:00+00:00", "proposal-0001", "accept"),
            {"id": "executed-0001", "kind": "executed", "ts": "2026-10-05T01:20:00+00:00", "role": "overseer",
             "ruling_id": "ruling-0001"},
            prop(2, "2026-10-05T02:00:00+00:00")]
    c = classify(recs)
    assert c.m1_status == {"proposal-0002": "after_accept"}
    # a prediction graded true does count as completion
    c2 = classify(recs, {"proposal-0001": {"signal": "s", "op": "gte", "status": "graded_true"}})
    assert c2.m1 == {}


def test_different_role_is_not_m1_but_duplicate_text_across_roles_is_m3_cross():
    recs = [prop(1, "2026-10-05T01:00:00+00:00", role="architect"),
            prop(2, "2026-10-05T02:00:00+00:00", role="quartermaster"),
            ruling(1, "2026-10-05T02:30:00+00:00", "proposal-0002", "reject",
                   "Duplicate of proposal-0001: the same action")]
    c = classify(recs)
    assert c.m1 == {}
    assert c.m3 == {} and c.m3_cross == {"proposal-0002"}


def test_m3_same_role_by_reject_reason_and_by_flag():
    recs = [prop(1, "2026-10-05T01:00:00+00:00"), prop(2, "2026-10-05T02:00:00+00:00", summary="x y z"),
            ruling(1, "2026-10-05T02:30:00+00:00", "proposal-0002", "reject", "It is already queued."),
            prop(3, "2026-10-05T03:00:00+00:00", summary="q w e", duplicate_of="proposal-0001")]
    c = classify(recs)
    assert set(c.m3) == {"proposal-0002", "proposal-0003"}


def test_window_is_counted_in_the_roles_own_wakes():
    base = "2026-10-0%dT00:00:00+00:00"
    recs = [prop(1, "2026-10-01T00:00:00+00:00"), prop(2, "2026-10-03T00:00:00+00:00")]
    runs = [{"run_id": f"run-{i}", "role": "quartermaster", "started_at": f"2026-10-01T0{i}:30:00+00:00"}
            for i in range(1, 10)]
    # fewer than 10 prior runs: the 7-day wall fallback applies, so it is a repeat
    assert classify(recs, runs=runs).m1 == {"proposal-0002": "proposal-0001"}
    # 11 runs of its own after the first proposal: the first falls out of the window
    runs = [{"run_id": f"run-{i}", "role": "quartermaster", "started_at": f"2026-10-02T{i:02d}:30:00+00:00"}
            for i in range(11)]
    assert classify(recs, runs=runs).m1 == {}


def test_repeat_defer_nothing_changed_and_answer_in_between():
    recs = [prop(1, "2026-10-05T01:00:00+00:00"),
            ruling(1, "2026-10-05T02:00:00+00:00", "proposal-0001", "defer"),
            ruling(2, "2026-10-05T03:00:00+00:00", "proposal-0001", "defer"),
            ruling(3, "2026-10-05T04:00:00+00:00", "proposal-0001", "defer")]
    assert classify(recs).m2 == {"ruling-0002": "proposal-0001", "ruling-0003": "proposal-0001"}
    recs.insert(3, {"id": "ask-0001", "kind": "ask", "ts": "2026-10-05T02:10:00+00:00", "role": "architect",
                    "proposal_id": "proposal-0001"})
    recs.insert(4, {"id": "answer-0001", "kind": "answer", "ts": "2026-10-05T02:20:00+00:00",
                    "role": "consultant", "ask_id": "ask-0001"})
    assert classify(recs).m2 == {"ruling-0003": "proposal-0001"}


def test_defer_across_an_epoch_boundary_is_a_change():
    recs = [prop(1, "2026-10-05T01:00:00+00:00"),
            ruling(1, "2026-10-05T02:00:00+00:00", "proposal-0001", "defer"),
            ruling(2, "2026-10-05T03:00:00+00:00", "proposal-0001", "defer")]
    epochs = [{"id": "e1", "since": "2026-10-05T02:30:00+00:00"}]
    assert wm.classify(recs, {}, [], epochs).m2 == {}


# ---- transcripts ------------------------------------------------------------


def allow():
    return {"quartermaster": {"read": {"stocks.availability", "orders.list"}, "write": {"queue.propose", "notebook.write"}}}


def tr(*rounds):
    return {"omitted_rounds": 0, "rounds": [
        {"n": i + 1, "usage": {"input": 10, "output": 5, "cacheRead": 1, "reasoningTokens": 2},
         "calls": [{"id": f"c{i}{j}", "name": n, "args": a, "error": e} for j, (n, a, e) in enumerate(calls)]}
        for i, calls in enumerate(rounds)]}


def test_redundant_reads_separated_by_a_write_are_not_redundant():
    t = tr([("df-quartermaster__stocks__availability", '{"type": "BARREL"}', False)],
           [("df-quartermaster__stocks__availability", '{"type":   "BARREL"}', False)],      # redundant (canonical args)
           [("df-quartermaster__queue__propose", "{}", False)],
           [("df-quartermaster__stocks__availability", '{"type": "BARREL"}', False)])        # after a write: fine
    m = wm.transcript_metrics(json.dumps(t), "quartermaster", allow(), set())
    assert (m["read_calls"], m["redundant_reads"]) == (3, 1)
    assert m["first_write_round"] == 3 and m["orientation_reads"] == 2
    assert m["tokens"]["output"] == 20 and m["rounds"] == 4


def test_failed_earlier_read_and_clipped_args():
    t = tr([("df-quartermaster__orders__list", "{...", True)],
           [("df-quartermaster__orders__list", "{...", False)],       # earlier errored: not redundant
           [("df-quartermaster__orders__list", "{...", False)])       # unparsable clipped args compared as strings
    m = wm.transcript_metrics(json.dumps(t), "quartermaster", allow(), set())
    assert m["redundant_reads"] == 1


def test_notebook_write_is_not_the_first_write():
    t = tr([("df-quartermaster__stocks__availability", "{}", False)],
           [("df-quartermaster__notebook__write", "{}", False)],
           [("df-quartermaster__queue__propose", "{}", False)])
    m = wm.transcript_metrics(json.dumps(t), "quartermaster", allow(), {"notebook.write"})
    assert m["first_write_round"] == 3


def test_omitted_rounds_count_and_no_transcript_is_none():
    t = tr([("df-quartermaster__orders__list", "{}", False)])
    t["omitted_rounds"] = 4
    m = wm.transcript_metrics(json.dumps(t), "quartermaster", allow(), set())
    assert m["rounds"] == 5 and m["truncated"]
    assert wm.transcript_metrics(None, "quartermaster", allow(), set()) is None


def test_wire_names_map_to_allowlist_ids_on_the_real_transcripts():
    """Red-team finding 12: calls must be non-empty and map to ids."""
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    al = wm.load_allowlists()
    for run_id, role in (("run-0022", "quartermaster"), ("run-0023", "overseer")):
        m = wm.transcript_metrics(json.dumps(fx["transcripts"][run_id]), role, al, set())
        assert m is not None and sum(m["calls"].values()) > 0, run_id
        assert m["unmapped"] == 0, (run_id, m["unmapped"])
        assert set(m["calls"]) <= al[role]["read"] | al[role]["write"]
    assert wm.wire_to_tool_id("df-overseer__queue__propose", {"queue.propose"}) == "queue.propose"
    assert wm.wire_to_tool_id("df-overseer__nope__x", {"queue.propose"}) is None


# ---- the report on fixture databases ---------------------------------------


def make_report(tmp_path, runs, records, preds=None, transcripts=None, **kw):
    q, r = tmp_path / "q.sqlite3", tmp_path / "r.sqlite3"
    write_queue(q, records, preds)
    write_runs(r, runs, transcripts)
    return wm.compute(q, r, epochs=EPOCHS, **kw), q, r


def small_world():
    recs = [prop(1, "2026-10-05T01:05:00+00:00"),
            ruling(1, "2026-10-05T01:30:00+00:00", "proposal-0001", "reject", "Duplicate of proposal-0009"),
            prop(2, "2026-10-05T02:05:00+00:00"),
            {"id": "pass-0001", "kind": "pass", "ts": "2026-10-05T03:05:00+00:00", "role": "architect"}]
    runs = [run(1, "quartermaster", "2026-10-05T01:00:00+00:00", "2026-10-05T01:10:00+00:00", ["proposal-0001"], cycle=1),
            run(2, "overseer", "2026-10-05T01:20:00+00:00", "2026-10-05T01:35:00+00:00", ["ruling-0001"], cycle=1),
            run(3, "quartermaster", "2026-10-05T02:00:00+00:00", "2026-10-05T02:10:00+00:00", ["proposal-0002"],
                cycle=2, cost_usd=None, status="timeout", timed_out=1),
            run(4, "architect", "2026-10-05T03:00:00+00:00", "2026-10-05T03:10:00+00:00", ["pass-0001"], cycle=3)]
    return recs, runs


def test_report_counts_killed_at_risk_pass_and_no_transcript(tmp_path):
    recs, runs = small_world()
    rep, *_ = make_report(tmp_path, runs, recs)
    assert rep["schema"] == "wake_metrics/1"
    qm = rep["by_role"]["quartermaster"]
    assert qm["wakes"] == 2 and qm["killed"] == 1
    assert qm["cost"]["n"] == 1 and qm["cost"]["sum"] == 0.05      # killed run not zeroed into cost
    assert qm["m1"] == 1 and qm["m3"] == 1 and qm["r"] == 2        # proposal-0002 repeat; proposal-0001 duplicate-rejected
    assert qm["at_risk_wakes"] == 1                                # only the wake with an earlier proposal outstanding
    assert qm["r_per_at_risk_wake"] == 1.0
    assert rep["by_role"]["architect"]["pass_rate"] == 1.0
    assert rep["totals"]["with_transcript"] == 0 and rep["by_role"]["quartermaster"]["rounds"]["n"] == 0
    assert rep["by_day"]["2026-10-05"]["quartermaster"]["wakes"] == 2
    assert rep["by_epoch"]["e1"]["overseer"]["wakes"] == 1
    assert rep["episodes"]["quartermaster"] == {"events": 2, "episodes": 1, "events_per_episode": 2.0}


def test_old_runs_database_without_transcript_column_reads(tmp_path):
    recs, runs = small_world()
    q, r = tmp_path / "q.sqlite3", tmp_path / "r.sqlite3"
    write_queue(q, recs)
    write_runs(r, runs, with_transcript_col=False)
    rep = wm.compute(q, r, epochs=EPOCHS)
    assert rep["totals"]["wakes"] == 4 and rep["totals"]["with_transcript"] == 0


def test_absent_files_give_an_empty_report(tmp_path):
    rep = wm.compute(tmp_path / "nope.q", tmp_path / "nope.r", epochs=[])
    assert rep["totals"]["wakes"] == 0 and rep["wakes"] == []
    assert not (tmp_path / "nope.q").exists() and not (tmp_path / "nope.r").exists()


def test_compute_is_read_only(tmp_path):
    recs, runs = small_world()
    q, r = tmp_path / "q.sqlite3", tmp_path / "r.sqlite3"
    write_queue(q, recs)
    write_runs(r, runs)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (q, r)]
    wm.compute(q, r, epochs=EPOCHS)
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (q, r)]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["q.sqlite3", "r.sqlite3"]


def test_since_filters_wakes_but_not_history(tmp_path):
    recs, runs = small_world()
    rep, *_ = make_report(tmp_path, runs, recs, since="2026-10-05T02:00:00+00:00")
    assert rep["totals"]["wakes"] == 2
    # the wake at 02:00 still sees the earlier proposal it repeats
    assert rep["by_role"]["quartermaster"]["m1"] == 1


SAFE = re.compile(r"^[A-Za-z0-9_.:+/\-]{0,80}$")


def strings(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(k, path + "/key")
            yield from strings(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v, path + "[]")
    elif isinstance(obj, str):
        yield path, obj


def test_every_published_string_is_an_id_or_keyword_not_text(tmp_path):
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    q, r = tmp_path / "q.sqlite3", tmp_path / "r.sqlite3"
    write_queue(q, fx["records"], fx["predictions"])
    write_runs(r, fx["runs"], fx["transcripts"])
    rep = wm.compute(q, r, epochs=EPOCHS)
    free_text = {"definitions", "notes"}
    for path, s in strings({k: v for k, v in rep.items() if k not in free_text}):
        if path.endswith("generated_at") or path.endswith("/since") or path.endswith("/until"):
            continue
        assert SAFE.match(s), (path, s)
    text = json.dumps(rep)
    for needle in ("Still", "Brew", "barrels", "Carpenter", "critically"):
        assert needle not in text, needle
    assert rep["totals"]["with_transcript"] == 2
    json.dumps(rep)  # serialisable


def test_text_report_and_cli(tmp_path, capsys):
    recs, runs = small_world()
    q, r = tmp_path / "q.sqlite3", tmp_path / "r.sqlite3"
    write_queue(q, recs)
    write_runs(r, runs)
    out = tmp_path / "m.json"
    pw = tmp_path / "pw.jsonl"
    assert wm.main(["--queue", str(q), "--runs", str(r), "--out", str(out), "--per-wake", str(pw), "--text"]) == 0
    assert json.loads(out.read_text())["schema"] == "wake_metrics/1"
    assert len(pw.read_text().strip().splitlines()) == 4
    assert "quartermaster" in capsys.readouterr().out


# ---- validation against the hand-labelled 2026-10-05..07 window ---------------


def prf(predicted: set, truth: set):
    tp = len(predicted & truth)
    p = tp / len(predicted) if predicted else None
    r = tp / len(truth) if truth else None
    return tp, len(predicted), len(truth), p, r


def test_validation_against_hand_labels(tmp_path):
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    lab = fx["labels"]
    window = set(lab["window_proposals"])
    c = wm.classify(fx["records"], fx["predictions"], fx["runs"], EPOCHS)
    got = {
        "m1": prf(set(c.m1) & window, set(lab["m1_repeat"])),
        "m1_wide": prf(set(c.m1_wide) & window, set(lab["m1_repeat"])),
        "m1_struct": prf(set(c.m1_struct) & window, set(lab["m1_repeat"])),
        "m3": prf(set(c.m3) & window, set(lab["m3"])),
        "m2": prf(set(c.m2), set(lab["m2"])),
    }
    # M3 and M2 reproduce the labels exactly.
    assert got["m3"][3] == 1.0 and got["m3"][4] == 1.0
    assert got["m2"][3] == 1.0 and got["m2"][4] == 1.0
    # The server's text rule never fires on this window: the roles paraphrase.
    assert got["m1"][1] == 0 and got["m1"][4] == 0.0
    # M1-wide (signal and operator) over-matches every drink-signal proposal.
    assert got["m1_wide"][4] >= 0.8 and got["m1_wide"][3] <= 0.5
    # The landmark-structured candidate: better precision, recall kept.
    assert got["m1_struct"][4] >= 0.8 and got["m1_struct"][3] > got["m1_wide"][3]
    print("VALIDATION", json.dumps(got))


def test_sweeps_cluster_back_to_back_runs_not_the_cycle_column():
    runs = [{"run_id": "a", "started_at": "2026-10-05T01:00:00+00:00", "ended_at": "2026-10-05T01:05:00+00:00"},
            {"run_id": "b", "started_at": "2026-10-05T01:05:10+00:00", "ended_at": "2026-10-05T01:08:00+00:00"},
            {"run_id": "c", "started_at": "2026-10-05T05:00:00+00:00", "ended_at": "2026-10-05T05:01:00+00:00"}]
    assert wm._sweeps(runs) == {"a": 1, "b": 1, "c": 2}
