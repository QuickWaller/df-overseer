"""The conductor's run reports through the live view and the publisher
(handoffs/2026-10-05-conductor-report.md): `strip` wake reason, `runs.json`,
the public-summary safety rule, change detection."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, REPO_ROOT)

import stream_publisher as sp  # noqa: E402
from dfqueue import live, runs, store  # noqa: E402
from dfqueue.tests._helpers import make_proposal  # noqa: E402

NOW_DT = datetime(2026, 10, 5, 12, 5, 0, tzinfo=timezone.utc)
NOW = NOW_DT.timestamp()


def _iso(delta_s):
    return (NOW_DT - timedelta(seconds=delta_s)).isoformat()


def _row(run_id, role, *, started=300, ended=None, **kw):
    row = {
        "run_id": run_id, "role": role, "wake_reason": "routine_review",
        "wake_detail": "internal detail", "cycle": 3, "started_at": _iso(started),
        "ended_at": None if ended is None else _iso(ended), "status": "ok", "ok": 1,
        "timed_out": 0, "duration_s": 42.4, "cost_usd": 0.031, "error": None,
        "final_answer": "Reviewed the fort. Filed one proposal for a second well.",
        "records_json": json.dumps([{"id": "proposal-0001", "kind": "proposal", "thread": "proposal-0001"}]),
    }
    row.update(kw)
    return row


def _call(role, tool, age):
    return {"ts": NOW - age, "role": role, "tool": tool, "is_error": False}


def test_open_run_gives_the_strip_its_wake_reason():
    rows = [_row("run-0002", "architect", started=60)]
    calls = [_call("architect", "overview.get", 10)]
    out = live.build_live(calls, NOW, public=True, runs=rows)
    assert out["awake"][0]["wake_reason"] == "routine_review"
    assert out["awake"][0]["run_id"] == "run-0002"
    assert out["source"].endswith("+reports")


def test_finished_run_fills_last_runs_and_cost_is_operator_only():
    rows = [_row("run-0001", "overseer", started=900, ended=860)]
    pub = live.build_live([], NOW, public=True, runs=rows)["last_runs"]["overseer"]
    op = live.build_live([], NOW, public=False, runs=rows)["last_runs"]["overseer"]
    assert pub["wake_reason"] == "routine_review" and pub["source"] == "report" and pub["ok"] is True
    assert "cost_usd" not in pub and op["cost_usd"] == 0.031


def test_a_report_with_no_end_for_too_long_is_lost_not_running():
    rows = [_row("run-0003", "architect", started=live.RUN_OPEN_MAX_AGE_S + 60)]
    out = live.build_runs(rows, NOW, public=True)
    assert out["runs"][0]["status"] == "lost"
    assert live.build_live([], NOW, public=True, runs=rows)["running"] is False


def test_no_run_store_changes_nothing():
    assert live.build_runs(None, NOW, public=True) is None
    out = live.build_live(None, NOW, public=True, runs=None)
    assert out["available"] is False


def test_public_runs_json_shape_and_the_summary_rule():
    rows = [
        _row("run-0001", "architect", started=900, ended=860),
        _row("run-0002", "consultant", started=800, ended=760,
             final_answer="Read https://example.org/x and the file /opt/df/secret for this."),
        _row("run-0003", "overseer", started=700, ended=660, ok=0, status="failed",
             error="boom", wake_reason="Free text, not a code!"),
    ]
    pub = live.build_runs(rows, NOW, public=True)
    by_id = {r["run_id"]: r for r in pub["runs"]}
    assert by_id["run-0001"]["summary"].startswith("Reviewed the fort.")
    assert by_id["run-0001"]["records"] == [{"id": "proposal-0001", "kind": "proposal", "thread": "proposal-0001"}]
    assert "summary" not in by_id["run-0002"] and by_id["run-0002"]["summary_withheld"] is True
    assert by_id["run-0003"]["status"] == "failed" and "summary" not in by_id["run-0003"]
    assert by_id["run-0003"]["wake_reason"] is None  # not a plain code
    assert pub["by_thread"]["proposal-0001"] == ["run-0001", "run-0002", "run-0003"]
    blob = json.dumps(pub)
    for forbidden in ("cost_usd", "wake_detail", "internal detail", "error", "boom", "example.org"):
        assert forbidden not in blob


def test_public_summary_is_cut_to_a_sentence_and_the_switch_turns_it_off(monkeypatch):
    long_answer = ("A short first sentence that stands alone and is fairly informative. " * 8).strip()
    s = live._public_summary(long_answer)
    assert len(s) <= live.SUMMARY_PUBLIC_MAX and s.endswith(".")
    monkeypatch.setattr(live, "PUBLIC_SUMMARIES", False)
    assert live._public_summary("Fine text.") is None
    pub = live.build_runs([_row("run-0001", "architect", ended=100)], NOW, public=True)
    assert pub["runs"][0]["summary_withheld"] is True


def test_operator_runs_json_has_cost_detail_error_and_full_summary():
    rows = [_row("run-0001", "architect", ended=100, final_answer="See /opt/x for detail. " * 30)]
    op = live.build_runs(rows, NOW, public=False)["runs"][0]
    assert op["cost_usd"] == 0.031 and op["wake_detail"] == "internal detail" and op["cycle"] == 3
    assert op["summary"].startswith("See /opt/x") and len(op["summary"]) > live.SUMMARY_PUBLIC_MAX


# ---- the publisher ---------------------------------------------------------


class _Pusher:
    def __init__(self):
        self.calls = []

    def __call__(self, local_dir, relay, *, delete=False, rsync_bin="rsync"):
        self.calls.append(str(local_dir))


def _seed(tmp_path):
    db = tmp_path / "queue.sqlite3"
    store.append(make_proposal(), db, game_tick=100)
    rp = runs.runs_path(db)
    run = runs.start_run(rp, role="architect", wake_reason="routine_review", wake_detail="d", cycle=1)
    runs.end_run(
        rp, run_id=run["run_id"], role=None, wake_reason=None, wake_detail=None, cycle=None,
        status="ok", ok=True, timed_out=False, duration_s=5.0, cost_usd=0.01, error=None,
        final_answer="Proposed a second well.",
        records=[{"id": "proposal-0001", "kind": "proposal", "thread": "proposal-0001"}],
    )
    return db


def test_run_cycle_writes_runs_json_for_both_sides_from_the_default_sibling_store(tmp_path):
    db = _seed(tmp_path)
    cfg = sp.PublisherConfig(db_path=str(db), staging_dir=str(tmp_path / "stage"))
    sp.run_cycle(cfg, now=NOW, pusher=_Pusher(), journal_reader=lambda: [])
    pub = json.loads((tmp_path / "stage/public/forts/queue/runs.json").read_text())
    op = json.loads((tmp_path / "stage/operator/forts/queue/runs.json").read_text())
    assert pub["runs"][0]["summary"] == "Proposed a second well."
    assert "cost_usd" not in pub["runs"][0] and op["runs"][0]["cost_usd"] == 0.01
    status = json.loads((tmp_path / "stage/public/forts/queue/status.json").read_text())
    assert status["live"]["last_runs"]["architect"]["source"] == "report"


def test_no_run_store_no_runs_json(tmp_path):
    db = tmp_path / "queue.sqlite3"
    store.append(make_proposal(), db, game_tick=100)
    cfg = sp.PublisherConfig(db_path=str(db), staging_dir=str(tmp_path / "stage"))
    sp.run_cycle(cfg, now=NOW, pusher=_Pusher())
    assert not (tmp_path / "stage/public/forts/queue/runs.json").exists()
    assert not (tmp_path / "stage/operator/forts/queue/runs.json").exists()


def test_a_new_run_report_triggers_a_push_and_an_unchanged_one_does_not(tmp_path):
    db = _seed(tmp_path)
    relay = sp.RelayTarget(host="<relay-vm-ip>", user="stream-pub", path="/srv/x", ssh_key=str(tmp_path / "k"))
    cfg = sp.PublisherConfig(db_path=str(db), staging_dir=str(tmp_path / "stage"),
                             public_relay=relay, operator_relay=relay, heartbeat_interval_seconds=10_000)
    pusher = _Pusher()
    sp.run_cycle(cfg, now=NOW, pusher=pusher, journal_reader=lambda: [])
    first = len(pusher.calls)
    sp.run_cycle(cfg, now=NOW + 5, pusher=pusher, journal_reader=lambda: [])
    assert len(pusher.calls) == first  # as_of ticking alone pushes nothing
    runs.start_run(runs.runs_path(db), role="overseer", wake_reason="ruling_due", wake_detail=None, cycle=2)
    sp.run_cycle(cfg, now=NOW + 10, pusher=pusher, journal_reader=lambda: [])
    assert len(pusher.calls) > first


def test_runs_db_env_and_flag_override_the_default(tmp_path):
    cfg = sp.config_from_env({"STREAM_PUBLISHER_DB": "/x/q.sqlite3", "STREAM_PUBLISHER_STAGING_DIR": "/s",
                              "STREAM_PUBLISHER_RUNS_DB": "/x/custom.sqlite3"})
    assert cfg.resolved_runs_db() == "/x/custom.sqlite3"
    assert sp.PublisherConfig(db_path=str(tmp_path / "q.sqlite3"), staging_dir="/s").resolved_runs_db() is None


# ---- "what it checked" (handoffs/2026-10-05-thread-run-data.md) -------------

TOOLS = {
    "overview.get": {"write": False, "description": "A first look at the fort. Counts and landmarks."},
    "zone.list": {"write": False, "description": "Lists zones."},
    "queue.propose": {"write": True, "description": "Files a proposal."},
}


def test_checks_are_reads_in_the_run_before_the_record_with_a_public_note():
    rows = [_row("run-0001", "architect", started=300, ended=100)]
    calls = [
        _call("architect", "overview.get", 280), _call("architect", "overview.get", 270),
        _call("architect", "zone.list", 250), _call("architect", "queue.propose", 200),
        _call("architect", "zone.list", 150),                      # after the record
        _call("overseer", "zone.list", 260),                       # other role
        _call("architect", "zone.list", 400),                      # before the run
    ]
    ts = {"proposal-0001": _iso(190)}
    for public in (True, False):
        out = live.build_runs(rows, NOW, public=public, calls=calls, tools=TOOLS, record_ts=ts)
        got = out["calls_by_record"]["proposal-0001"]
        assert [(c["tool"], c["n"], c["failed"]) for c in got] == [("overview.get", 2, False), ("zone.list", 1, False)]
        assert got[0]["note"] == "A first look at the fort."
        assert "arguments" not in json.dumps(out)


def test_a_failed_read_is_flagged_and_no_journal_means_no_checks():
    rows = [_row("run-0001", "architect", started=300, ended=100)]
    bad = [{"ts": NOW - 250, "role": "architect", "tool": "zone.list", "is_error": True}]
    out = live.build_runs(rows, NOW, public=True, calls=bad, tools=TOOLS, record_ts={"proposal-0001": _iso(190)})
    assert out["calls_by_record"]["proposal-0001"][0]["failed"] is True
    assert live.build_runs(rows, NOW, public=True)["calls_by_record"] == {}
