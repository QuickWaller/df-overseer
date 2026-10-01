"""Tests for `scripts/stream_publisher.py`, the stream page's real publisher
(slice S1, `handoffs/2026-10-01-stream-page-s1-prep.md`). All against local
files only -- no network, no real `rsync`/`ssh` process ever runs; every
test that would push supplies a fake `pusher` callable instead
(`run_cycle`'s own injection point, the same reason `_rsync_push` is a
free function rather than inlined).

Covers: change detection (a second cycle with identical queue content does
not push again), the kill-switch file (stops both sides outright), the
`public_enabled=False` switch (stops and clears only the public side, keeps
the operator side running), safe-on-restart (a missing/corrupt cursor file
costs one extra push, never a crash), the multi-fort layout (`forts.json`
plus `forts/<fort-id>/...` on both sides, fort id defaulting to the `--db`
file's own stem and overridable, fort name/status configurable), and -- the
one safety property this handoff calls out by name -- that the publisher
never attempts to write to the queue database at all, proved by actually
making the on-disk file read-only and running a full cycle against it.
"""

from __future__ import annotations

import json
import os
import stat
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import pytest

import stream_publisher as sp  # noqa: E402

sys.path.insert(0, REPO_ROOT)
from dfqueue import store  # noqa: E402
from dfqueue.tests._helpers import (  # noqa: E402
    make_executed, make_project, make_proposal, make_ruling,
)


def _seed_db(path):
    store.append(make_proposal(), path, game_tick=100)
    ruling = store.append(make_ruling(proposal_id="proposal-0001"), path)
    project = store.append(make_project(from_ruling=ruling["id"]), path)
    return ruling, project


def _cfg(tmp_path, **overrides):
    kwargs = dict(
        db_path=str(tmp_path / "queue.sqlite3"),
        staging_dir=str(tmp_path / "stage"),
    )
    kwargs.update(overrides)
    return sp.PublisherConfig(**kwargs)


class _RecordingPusher:
    """A fake `pusher` -- records every call instead of touching the
    network, so a test can assert exactly what WOULD have been pushed."""

    def __init__(self):
        self.calls = []

    def __call__(self, local_dir, relay, *, delete=False, rsync_bin="rsync"):
        self.calls.append({
            "local_dir": str(local_dir), "relay": relay, "delete": delete,
        })


def _relay(tmp_path, name):
    return sp.RelayTarget(
        host="<relay-vm-ip>", user="stream-pub",
        path=f"/srv/stream/data/{name}", ssh_key=str(tmp_path / "key"),
    )


# ---- config -----------------------------------------------------------------


def test_config_from_env_requires_db_and_staging_dir_by_default():
    with pytest.raises(sp.ConfigError):
        sp.config_from_env({})


def test_config_from_env_validate_false_allows_an_incomplete_config():
    cfg = sp.config_from_env({}, validate=False)
    assert cfg.db_path == ""
    assert cfg.staging_dir == ""


def test_config_from_env_reads_every_field():
    env = {
        "STREAM_PUBLISHER_DB": "/var/lib/dfqueue/fort.sqlite3",
        "STREAM_PUBLISHER_STAGING_DIR": "/var/lib/stream-publisher/stage",
        "STREAM_PUBLISHER_KILL_SWITCH_FILE": "/var/lib/stream-publisher/STOP",
        "STREAM_PUBLISHER_PUBLIC_ENABLED": "false",
        "STREAM_PUBLISHER_HEARTBEAT_SECONDS": "30",
        "STREAM_PUBLISHER_LOOP_SECONDS": "10",
        "STREAM_PUBLISHER_PUBLIC_RELAY_HOST": "<relay-vm-ip>",
        "STREAM_PUBLISHER_PUBLIC_RELAY_USER": "stream-pub",
        "STREAM_PUBLISHER_PUBLIC_RELAY_PATH": "/srv/stream/data/public",
        "STREAM_PUBLISHER_PUBLIC_RELAY_SSH_KEY": "/etc/stream-publisher/key",
    }
    cfg = sp.config_from_env(env)
    assert cfg.db_path == "/var/lib/dfqueue/fort.sqlite3"
    assert cfg.public_enabled is False
    assert cfg.heartbeat_interval_seconds == 30
    assert cfg.loop_interval_seconds == 10
    assert cfg.public_relay == sp.RelayTarget(
        host="<relay-vm-ip>", user="stream-pub",
        path="/srv/stream/data/public", ssh_key="/etc/stream-publisher/key",
    )
    assert cfg.operator_relay is None


def test_config_from_env_rejects_a_partially_configured_relay():
    env = {
        "STREAM_PUBLISHER_DB": "x", "STREAM_PUBLISHER_STAGING_DIR": "y",
        "STREAM_PUBLISHER_PUBLIC_RELAY_HOST": "<relay-vm-ip>",
        # user/path/ssh_key all missing
    }
    with pytest.raises(sp.ConfigError):
        sp.config_from_env(env)


def test_config_from_env_reads_fort_fields():
    env = {
        "STREAM_PUBLISHER_DB": "x", "STREAM_PUBLISHER_STAGING_DIR": "y",
        "STREAM_PUBLISHER_FORT_ID": "uniboslan",
        "STREAM_PUBLISHER_FORT_NAME": "Ragwind",
        "STREAM_PUBLISHER_FORT_STATUS": "lost",
    }
    cfg = sp.config_from_env(env)
    assert cfg.fort_id == "uniboslan"
    assert cfg.fort_name == "Ragwind"
    assert cfg.fort_status == "lost"


def test_fort_id_defaults_unset_and_name_status_default_sensibly():
    cfg = sp.config_from_env(
        {"STREAM_PUBLISHER_DB": "x", "STREAM_PUBLISHER_STAGING_DIR": "y"}
    )
    assert cfg.fort_id == ""
    assert cfg.fort_name == sp.DEFAULT_FORT_NAME
    assert cfg.fort_status == "live"


def test_resolved_fort_id_falls_back_to_the_db_files_own_stem(tmp_path):
    cfg = _cfg(tmp_path, db_path=str(tmp_path / "Uniboslan.sqlite3"))
    assert cfg.resolved_fort_id() == "Uniboslan"


def test_resolved_fort_id_prefers_an_explicitly_configured_one(tmp_path):
    cfg = _cfg(
        tmp_path, db_path=str(tmp_path / "Uniboslan.sqlite3"), fort_id="ragwind",
    )
    assert cfg.resolved_fort_id() == "ragwind"


def test_config_from_env_rejects_an_invalid_fort_status():
    env = {
        "STREAM_PUBLISHER_DB": "x", "STREAM_PUBLISHER_STAGING_DIR": "y",
        "STREAM_PUBLISHER_FORT_STATUS": "paused",
    }
    with pytest.raises(sp.ConfigError):
        sp.config_from_env(env)


def test_config_from_env_rejects_an_invalid_boolean():
    env = {
        "STREAM_PUBLISHER_DB": "x", "STREAM_PUBLISHER_STAGING_DIR": "y",
        "STREAM_PUBLISHER_PUBLIC_ENABLED": "maybe",
    }
    with pytest.raises(sp.ConfigError):
        sp.config_from_env(env)


# ---- content hashing ----------------------------------------------------


def test_content_hash_is_stable_for_identical_content():
    items = [{"seq": 1, "text": "a"}]
    projects = {"projects": {}}
    status = {"available": False}
    assert sp.compute_content_hash(items, projects, status) == sp.compute_content_hash(
        list(items), dict(projects), dict(status)
    )


def test_content_hash_changes_when_items_change():
    base = sp.compute_content_hash([{"seq": 1}], {}, None)
    changed = sp.compute_content_hash([{"seq": 1}, {"seq": 2}], {}, None)
    assert base != changed


# ---- build_projection / step-progress merge -----------------------------


def test_build_projection_merges_counts_into_every_projection(tmp_path):
    db = tmp_path / "queue.sqlite3"
    ruling, project = _seed_db(db)
    s1 = project["steps"][0]["id"]
    store.append(
        make_executed(
            ruling_id=ruling["id"], cycle=9, step_id=s1,
            actions=[{
                "tool": "construction.mine-vein", "outcome": "success",
                "targets": ["ring-13-ore-1", "ring-13-ore-2", "ring-13-ore-3"],
                "target_state": "done",
            }],
        ),
        db,
    )
    from dfqueue import feed, feed_status

    records = feed.load_records_readonly(db)
    statuses = feed_status.all_project_statuses_readonly(db)

    _, public_projects = sp.build_projection(records, public=True, project_statuses=statuses)
    _, operator_projects = sp.build_projection(records, public=False, project_statuses=statuses)

    pub_entry = public_projects["projects"][project["id"]]
    op_entry = operator_projects["projects"][project["id"]]
    assert pub_entry["counts"] == {"done": 3}
    assert op_entry["counts"] == {"done": 3}
    # top_blocker is operator-only (design §3.3 item 7: free-text reason).
    assert "top_blocker" not in pub_entry
    assert "top_blocker" in op_entry


# ---- run_cycle: writes locally even with no relay configured ------------


def test_run_cycle_with_no_relay_writes_locally_and_pushes_nothing(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    cfg = _cfg(tmp_path)

    result = sp.run_cycle(cfg, now=1000.0)

    assert result["operator"]["reason"] == "no_relay_configured"
    assert result["public"]["reason"] == "no_relay_configured"
    assert not result["operator"]["pushed"] and not result["public"]["pushed"]
    assert (tmp_path / "stage" / "public" / "forts.json").is_file()
    assert (tmp_path / "stage" / "public" / "forts" / "queue" / "head.json").is_file()
    assert (tmp_path / "stage" / "operator" / "forts" / "queue" / "head.json").is_file()


def test_run_cycle_writes_forts_json_with_the_resolved_fort(tmp_path):
    db = tmp_path / "Uniboslan.sqlite3"
    _seed_db(db)
    cfg = _cfg(tmp_path, db_path=str(db), fort_name="Ragwind", fort_status="live")

    sp.run_cycle(cfg, now=1000.0)

    for side in ("public", "operator"):
        forts = json.loads((tmp_path / "stage" / side / "forts.json").read_text())
        assert forts == {
            "forts": [{"id": "Uniboslan", "name": "Ragwind", "status": "live", "current": True}]
        }
        assert (tmp_path / "stage" / side / "forts" / "Uniboslan" / "head.json").is_file()


def test_run_cycle_honours_an_explicit_fort_id_over_the_db_stem(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    cfg = _cfg(tmp_path, db_path=str(db), fort_id="ragwind")

    sp.run_cycle(cfg, now=1000.0)

    assert (tmp_path / "stage" / "public" / "forts" / "ragwind" / "head.json").is_file()
    assert not (tmp_path / "stage" / "public" / "forts" / "queue").exists()


# ---- run_cycle: change detection -----------------------------------------


def test_run_cycle_pushes_on_first_run_then_skips_an_unchanged_second_run(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
    )

    first = sp.run_cycle(cfg, now=1000.0, pusher=pusher)
    assert first["public"]["pushed"] and first["operator"]["pushed"]
    assert len(pusher.calls) == 2

    second = sp.run_cycle(cfg, now=1001.0, pusher=pusher)
    assert second["public"]["reason"] == "unchanged"
    assert second["operator"]["reason"] == "unchanged"
    assert len(pusher.calls) == 2  # no new calls


def test_run_cycle_pushes_again_when_the_queue_actually_changes(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
    )
    sp.run_cycle(cfg, now=1000.0, pusher=pusher)

    store.append(make_proposal(), db, game_tick=200)

    second = sp.run_cycle(cfg, now=1001.0, pusher=pusher)
    assert second["public"]["pushed"]
    assert second["operator"]["pushed"]  # the new proposal changes both projections
    assert len(pusher.calls) == 4


def test_run_cycle_heartbeats_even_with_no_change(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
        heartbeat_interval_seconds=60,
    )
    sp.run_cycle(cfg, now=1000.0, pusher=pusher)
    assert len(pusher.calls) == 2

    # Well within the heartbeat window: no push.
    sp.run_cycle(cfg, now=1010.0, pusher=pusher)
    assert len(pusher.calls) == 2

    # Past the heartbeat window: pushes again even though nothing changed.
    third = sp.run_cycle(cfg, now=1070.0, pusher=pusher)
    assert third["public"]["pushed"] and third["operator"]["pushed"]
    assert len(pusher.calls) == 4


# ---- the kill-switch file: stops everything -------------------------------


def test_kill_switch_file_stops_both_sides(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    kill_switch = tmp_path / "STOP"
    kill_switch.write_text("", encoding="utf-8")
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
        kill_switch_file=str(kill_switch),
    )

    result = sp.run_cycle(cfg, now=1000.0, pusher=pusher)

    assert result["kill_switch_active"] is True
    assert result["public"]["reason"] == "kill_switch_file"
    assert result["operator"]["reason"] == "kill_switch_file"
    assert pusher.calls == []
    # Local staging is still written -- an operator can inspect it.
    assert (tmp_path / "stage" / "public" / "forts" / "queue" / "head.json").is_file()


def test_kill_switch_file_absent_does_not_block_publishing(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
        kill_switch_file=str(tmp_path / "does-not-exist"),
    )

    result = sp.run_cycle(cfg, now=1000.0, pusher=pusher)
    assert result["kill_switch_active"] is False
    assert result["public"]["pushed"] and result["operator"]["pushed"]


# ---- public_enabled=False: stops and clears only the public side --------


def test_public_disabled_clears_public_but_keeps_operator_running(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
        public_enabled=False,
    )

    result = sp.run_cycle(cfg, now=1000.0, pusher=pusher)

    assert result["public"]["pushed"] is True
    assert result["operator"]["pushed"] is True
    public_call = [c for c in pusher.calls if c["relay"].path.endswith("public")][0]
    assert public_call["delete"] is True  # design §4.6 layer 2: segments removed
    head = json.loads(
        (tmp_path / "stage" / "public" / "forts" / "queue" / "head.json").read_text()
    )
    assert head["state"] == "off"

    # A second cycle, still disabled and unchanged: no further push until
    # the heartbeat window (already "off", nothing new to clear).
    second = sp.run_cycle(cfg, now=1001.0, pusher=pusher)
    assert second["public"]["reason"] == "already_off"
    assert len(pusher.calls) == 2  # one public, one operator -- no new public push


# ---- restart safety: a missing or corrupt cursor costs one push, not a crash --


def test_a_missing_cursor_file_is_treated_as_a_fresh_start(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    pusher = _RecordingPusher()
    cfg = _cfg(
        tmp_path, public_relay=_relay(tmp_path, "public"),
        operator_relay=_relay(tmp_path, "operator"),
    )
    sp.run_cycle(cfg, now=1000.0, pusher=pusher)
    assert len(pusher.calls) == 2

    (tmp_path / "stage" / sp.CURSOR_FILENAME).unlink()

    second = sp.run_cycle(cfg, now=1001.0, pusher=pusher)
    assert second["public"]["pushed"] and second["operator"]["pushed"]
    assert len(pusher.calls) == 4  # pushed again -- identical bytes, no data lost


def test_a_corrupt_cursor_file_does_not_crash_the_cycle(tmp_path):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    staging = tmp_path / "stage"
    staging.mkdir(parents=True)
    (staging / sp.CURSOR_FILENAME).write_text("not json {{{", encoding="utf-8")
    cfg = _cfg(tmp_path)

    result = sp.run_cycle(cfg, now=1000.0)  # must not raise
    assert result["operator"]["reason"] == "no_relay_configured"


# ---- never writes to the queue -------------------------------------------


def test_run_cycle_succeeds_against_an_on_disk_read_only_database(tmp_path):
    """The strongest proof available: make the queue file read-only AT THE
    FILESYSTEM LEVEL (not just via the SQLite URI this module already uses)
    and run a full cycle against it. If anything in the publisher's path
    ever tried to write to the queue -- a stray `store.append`, an
    `_ensure_schema` triggered by `store._connect` -- this would raise
    `sqlite3.OperationalError`/`PermissionError` instead of succeeding."""
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    os.chmod(db, stat.S_IREAD)
    try:
        cfg = _cfg(tmp_path, staging_dir=str(tmp_path / "stage"))
        result = sp.run_cycle(cfg, now=1000.0)
        assert result["operator"]["reason"] == "no_relay_configured"
    finally:
        os.chmod(db, stat.S_IWRITE | stat.S_IREAD)  # allow tmp_path cleanup


def test_module_imports_no_queue_write_function():
    """A cheap static guard alongside the behavioural proof above: this
    module must never import `dfqueue.store.append` or `dfqueue.store._connect`
    by name, which would make an accidental write one refactor away from
    reachable even if no code path calls it today."""
    import dfqueue.store as store_module

    for name in dir(sp):
        value = getattr(sp, name)
        assert value is not store_module.append
        assert value is not store_module._connect


# ---- CLI -------------------------------------------------------------------


def test_config_from_args_merges_flags_over_env(tmp_path, monkeypatch):
    monkeypatch.delenv("STREAM_PUBLISHER_DB", raising=False)
    monkeypatch.delenv("STREAM_PUBLISHER_STAGING_DIR", raising=False)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    parser = sp._build_arg_parser()
    args = parser.parse_args([
        "--db", str(tmp_path / "q.sqlite3"),
        "--staging-dir", str(tmp_path / "stage"),
        "--env-file", str(empty_env),
    ])
    cfg = sp._config_from_args(args)
    assert cfg.db_path == str(tmp_path / "q.sqlite3")
    assert cfg.staging_dir == str(tmp_path / "stage")


def test_config_from_args_rejects_a_half_specified_relay_flag_set(tmp_path):
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    parser = sp._build_arg_parser()
    args = parser.parse_args([
        "--db", str(tmp_path / "q.sqlite3"),
        "--staging-dir", str(tmp_path / "stage"),
        "--env-file", str(empty_env),
        "--public-relay-host", "<relay-vm-ip>",
    ])
    with pytest.raises(sp.ConfigError):
        sp._config_from_args(args)


def test_main_once_prints_a_json_summary_and_returns_zero(tmp_path, capsys):
    db = tmp_path / "queue.sqlite3"
    _seed_db(db)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    rc = sp.main([
        "--once", "--db", str(db), "--staging-dir", str(tmp_path / "stage"),
        "--env-file", str(empty_env),
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["operator"]["reason"] == "no_relay_configured"


def test_main_returns_2_on_a_config_error(tmp_path, capsys):
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    rc = sp.main(["--once", "--env-file", str(empty_env)])
    assert rc == 2
    assert "db_path" in capsys.readouterr().err
