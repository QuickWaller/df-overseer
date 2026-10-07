"""`metrics.json` through the publisher (handoffs/2026-10-07-metrics-tab.md):
written for both sides from the live DBs, schema-checked, recomputed on a
slower cadence than the feed, and never allowed to stop a cycle."""
from __future__ import annotations

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
sys.path.insert(0, REPO_ROOT)

import stream_publisher as sp  # noqa: E402
from dfqueue import runs, store  # noqa: E402
from dfqueue.tests._helpers import make_proposal  # noqa: E402

NOW = 1_790_000_000.0
SAFE = re.compile(r"^[A-Za-z0-9_.:+/\-]{0,80}$")
TOP_KEYS = {"schema", "generated_at", "since", "until", "definitions", "totals", "by_role", "by_day",
            "by_epoch", "episodes", "interval", "power", "tool_usage", "wakes", "unattributed", "notes"}


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


def _cfg(tmp_path, db, **kw):
    return sp.PublisherConfig(db_path=str(db), staging_dir=str(tmp_path / "stage"), **kw)


def _strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
    elif isinstance(obj, str):
        yield obj


def test_metrics_json_written_for_both_sides_and_matches_the_schema(tmp_path):
    db = _seed(tmp_path)
    sp.run_cycle(_cfg(tmp_path, db), now=NOW, pusher=_Pusher(), journal_reader=lambda: [])
    pub = json.loads((tmp_path / "stage/public/forts/queue/metrics.json").read_text())
    op = json.loads((tmp_path / "stage/operator/forts/queue/metrics.json").read_text())
    assert pub == op
    assert pub["schema"] == "wake_metrics/1" and TOP_KEYS <= set(pub)
    assert pub["totals"]["wakes"] == 1 and "architect" in pub["by_role"]
    # The published strings are ids and keywords, never prose (the module's own rule).
    free = ("definitions", "notes", "generated_at", "since", "until")
    for s in _strings({k: v for k, v in pub.items() if k not in free}):
        assert SAFE.match(s), s


def test_no_run_store_no_metrics_json(tmp_path):
    db = tmp_path / "queue.sqlite3"
    store.append(make_proposal(), db, game_tick=100)
    sp.run_cycle(_cfg(tmp_path, db), now=NOW, pusher=_Pusher())
    assert not (tmp_path / "stage/public/forts/queue/metrics.json").exists()
    assert not (tmp_path / "stage/operator/forts/queue/metrics.json").exists()


def test_metrics_recompute_waits_for_the_interval(tmp_path, monkeypatch):
    from dfqueue import wake_metrics
    db = _seed(tmp_path)
    calls = []
    real = wake_metrics.compute
    monkeypatch.setattr(wake_metrics, "compute", lambda *a, **k: calls.append(1) or real(*a, **k))
    cfg = _cfg(tmp_path, db, metrics_interval_seconds=600)
    sp.run_cycle(cfg, now=NOW, pusher=_Pusher(), journal_reader=lambda: [])
    sp.run_cycle(cfg, now=NOW + 60, pusher=_Pusher(), journal_reader=lambda: [])
    assert len(calls) == 1
    sp.run_cycle(cfg, now=NOW + 601, pusher=_Pusher(), journal_reader=lambda: [])
    assert len(calls) == 2


def test_a_metrics_failure_never_stops_the_cycle(tmp_path, monkeypatch):
    from dfqueue import wake_metrics

    def boom(*a, **k):
        raise RuntimeError("bad db")
    monkeypatch.setattr(wake_metrics, "compute", boom)
    db = _seed(tmp_path)
    sp.run_cycle(_cfg(tmp_path, db), now=NOW, pusher=_Pusher(), journal_reader=lambda: [])
    assert (tmp_path / "stage/public/forts/queue/runs.json").exists()
    assert not (tmp_path / "stage/public/forts/queue/metrics.json").exists()


def test_generated_at_alone_does_not_trigger_a_push(tmp_path):
    db = _seed(tmp_path)
    relay = sp.RelayTarget(host="<relay-vm-ip>", user="stream-pub", path="/srv/x", ssh_key=str(tmp_path / "k"))
    cfg = _cfg(tmp_path, db, public_relay=relay, operator_relay=relay,
               heartbeat_interval_seconds=10_000, metrics_interval_seconds=0)
    pusher = _Pusher()
    sp.run_cycle(cfg, now=NOW, pusher=pusher, journal_reader=lambda: [])
    first = len(pusher.calls)
    sp.run_cycle(cfg, now=NOW + 5, pusher=pusher, journal_reader=lambda: [])
    assert len(pusher.calls) == first


def test_metrics_interval_env_and_flag():
    cfg = sp.config_from_env({"STREAM_PUBLISHER_DB": "/x/q.sqlite3", "STREAM_PUBLISHER_STAGING_DIR": "/s",
                              "STREAM_PUBLISHER_METRICS_SECONDS": "900"})
    assert cfg.metrics_interval_seconds == 900
    args = sp._build_arg_parser().parse_args(["--metrics-interval", "0", "--db", "/x/q", "--staging-dir", "/s"])
    assert sp._config_from_args(args).metrics_interval_seconds == 0
