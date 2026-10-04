"""The who-is-awake live view through the publisher
(handoffs/2026-10-05-board-order-year-live-view.md). Journal and conductor
copy are injected; nothing here touches journald."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import pytest

import stream_publisher as sp  # noqa: E402

sys.path.insert(0, REPO_ROOT)
from dfqueue import store  # noqa: E402
from dfqueue.tests._helpers import make_project, make_proposal, make_ruling  # noqa: E402

NOW = datetime(2026, 10, 5, 12, 5, 0, tzinfo=timezone.utc).timestamp()


def _seed_db(path):
    store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(make_ruling(proposal_id="proposal-0001"), path)
    store.append(make_project(from_ruling=ruling["id"]), path)


def _cfg(tmp_path, **overrides):
    kwargs = dict(db_path=str(tmp_path / "queue.sqlite3"), staging_dir=str(tmp_path / "stage"))
    kwargs.update(overrides)
    return sp.PublisherConfig(**kwargs)


class _Pusher:
    def __init__(self):
        self.calls = []

    def __call__(self, local_dir, relay, *, delete=False, rsync_bin="rsync"):
        self.calls.append(str(local_dir))


def _relay(tmp_path, name):
    return sp.RelayTarget(host="<relay-vm-ip>", user="stream-pub",
                          path=f"/srv/stream/data/{name}", ssh_key=str(tmp_path / "key"))


def _line(age_s, role, tool):
    ts = datetime.fromtimestamp(NOW - age_s, timezone.utc).isoformat()
    return json.dumps({
        "event": "tools/call", "ts": ts, "role": role, "tool": tool, "tool_id": tool,
        "arguments": {"password": "ARG-SECRET"}, "client": "10.1.2.3", "is_error": False,
    })


def _status(tmp_path, side):
    return (tmp_path / "stage" / side / "forts" / "queue" / "status.json").read_text()


def test_off_by_default_status_stays_the_placeholder(tmp_path):
    _seed_db(tmp_path / "queue.sqlite3")
    sp.run_cycle(_cfg(tmp_path), now=NOW, journal_reader=lambda: pytest.fail("journal read while off"))
    assert "live" not in json.loads(_status(tmp_path, "public"))


def test_live_lands_in_both_status_files_public_without_cost_or_arguments(tmp_path):
    _seed_db(tmp_path / "queue.sqlite3")
    cdir = tmp_path / "conductor" / "cycles" / "cycle-000001-x"
    cdir.mkdir(parents=True)
    (cdir / "run-overseer.json").write_text(
        json.dumps({"role": "overseer", "wall_clock_seconds": 60.0, "cost_usd": 3.21}))
    cfg = _cfg(tmp_path, live_journal=True, conductor_dir=str(tmp_path / "conductor"))
    sp.run_cycle(cfg, now=NOW, journal_reader=lambda: [_line(120, "architect", "zone.list")])

    pub_text, op_text = _status(tmp_path, "public"), _status(tmp_path, "operator")
    pub, op = json.loads(pub_text), json.loads(op_text)
    assert pub["live"]["running"] and pub["live"]["awake"][0]["last_tool"] == "zone.list"
    assert pub["live"]["awake"][0]["elapsed_s"] == 120
    for secret in ("3.21", "ARG-SECRET", "10.1.2.3"):
        assert secret not in pub_text
    assert op["live"]["last_runs"]["overseer"]["cost_usd"] == 3.21


def test_unreadable_journal_does_not_fail_the_cycle(tmp_path):
    _seed_db(tmp_path / "queue.sqlite3")
    sp.run_cycle(_cfg(tmp_path, live_journal=True), now=NOW, journal_reader=lambda: None)
    assert json.loads(_status(tmp_path, "public"))["live"]["available"] is False


def test_a_ticking_clock_alone_does_not_force_a_push(tmp_path):
    _seed_db(tmp_path / "queue.sqlite3")
    cfg = _cfg(tmp_path, live_journal=True, public_relay=_relay(tmp_path, "pub"),
               operator_relay=_relay(tmp_path, "op"), heartbeat_interval_seconds=10_000)
    pusher = _Pusher()
    sp.run_cycle(cfg, now=NOW, pusher=pusher, journal_reader=lambda: [_line(30, "architect", "zone.list")])
    first = len(pusher.calls)
    assert first == 2
    # five seconds later the same call is five seconds older; nothing real changed
    sp.run_cycle(cfg, now=NOW + 5, pusher=pusher, journal_reader=lambda: [_line(30, "architect", "zone.list")])
    assert len(pusher.calls) == first


def test_env_reads_live_settings():
    cfg = sp.config_from_env({
        "STREAM_PUBLISHER_DB": "d", "STREAM_PUBLISHER_STAGING_DIR": "s",
        "STREAM_PUBLISHER_LIVE_JOURNAL": "true", "STREAM_PUBLISHER_CONDUCTOR_DIR": "/c",
    })
    assert cfg.live_journal is True and cfg.conductor_dir == "/c"
