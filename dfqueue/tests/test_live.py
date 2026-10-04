import json
import subprocess
from datetime import datetime, timezone

from dfqueue import live

T0 = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc).timestamp()


def _line(offset, role, tool, *, error=False, args=None):
    ts = datetime.fromtimestamp(T0 + offset, timezone.utc).isoformat(timespec="milliseconds")
    return json.dumps({
        "event": "tools/call", "ts": ts, "role": role, "tool": tool.replace(".", "_"),
        "tool_id": tool, "arguments": args or {"secret": "ARG-VALUE"}, "client": "203.0.113.9",
        "session_id": "sess-1", "is_error": error, "duration_ms": 5.0,
    })


def test_parse_skips_junk_and_drops_arguments():
    lines = ["garbage", '{"event": "other"}', _line(0, "architect", "zone.list"), '{"event": "tools/call", bad']
    calls = live.parse_call_lines(lines)
    assert calls == [{"ts": T0, "role": "architect", "tool": "zone.list", "is_error": False}]
    assert "ARG-VALUE" not in json.dumps(calls)


def test_awake_role_burst_start_elapsed_and_last_tool():
    lines = [_line(o, "architect", t) for o, t in [(0, "overview.get"), (100, "zone.list"), (300, "tree.find")]]
    out = live.build_live(live.parse_call_lines(lines), T0 + 330, public=True)
    assert out["available"] and out["running"]
    [a] = out["awake"]
    assert a["role"] == "architect" and a["elapsed_s"] == 330 and a["last_tool"] == "tree.find"
    assert a["since"].startswith("2026-10-05T12:00:00")
    assert "last_error" not in a


def test_gap_longer_than_window_splits_a_run_and_old_burst_is_the_last_run():
    lines = [_line(0, "overseer", "a.b"), _line(60, "overseer", "a.c"), _line(1000, "overseer", "a.d")]
    out = live.build_live(live.parse_call_lines(lines), T0 + 1010, public=True)
    [a] = out["awake"]
    assert a["elapsed_s"] == 10
    assert out["last_runs"]["overseer"]["duration_s"] == 60


def test_idle_after_window_and_run_duration_from_calls():
    lines = [_line(0, "consultant", "doctrine.get"), _line(90, "consultant", "doctrine.get")]
    out = live.build_live(live.parse_call_lines(lines), T0 + 90 + live.AWAKE_WINDOW_S + 1, public=True)
    assert out["available"] and not out["running"] and out["awake"] == []
    assert out["last_runs"]["consultant"]["duration_s"] == 90


def test_conductor_alone_counts_as_running_but_is_not_listed_as_a_role():
    out = live.build_live(live.parse_call_lines([_line(0, "conductor", "clock.status")]), T0 + 10, public=True)
    assert out["running"] and out["awake"] == []


def test_unreadable_journal_is_unavailable_not_an_error():
    out = live.build_live(None, T0, public=True)
    assert out["available"] is False and out["reason"] == "journal_unreadable"


def test_public_has_no_cost_or_error_flag_operator_does():
    calls = live.parse_call_lines([_line(0, "architect", "zone.list", error=True)])
    conductor = {"running": None, "last_runs": {"architect": {
        "duration_s": 361.4, "cost_usd": 1.25, "wake_reason": "pending_proposal", "ok": True, "ended_at": "x"}}}
    pub = live.build_live(calls, T0 + 5, public=True, conductor=conductor)
    op = live.build_live(calls, T0 + 5, public=False, conductor=conductor)
    assert "cost_usd" not in json.dumps(pub) and "last_error" not in json.dumps(pub)
    assert op["last_runs"]["architect"]["cost_usd"] == 1.25 and op["awake"][0]["last_error"] is True
    assert pub["last_runs"]["architect"]["duration_s"] == 361
    assert pub["last_runs"]["architect"]["wake_reason"] == "pending_proposal"


def test_running_block_supplies_the_wake_reason_while_awake():
    calls = live.parse_call_lines([_line(0, "architect", "zone.list")])
    started = datetime.fromtimestamp(T0 - 5, timezone.utc).isoformat()
    conductor = {"running": {"role": "architect", "wake_reason": "routine_review", "started_at": started},
                 "last_runs": {}}
    out = live.build_live(calls, T0 + 10, public=True, conductor=conductor)
    assert out["awake"][0]["wake_reason"] == "routine_review"
    stale = live.build_live(calls, T0 + 10 + live.RUNNING_BLOCK_MAX_AGE_S, public=True, conductor=conductor)
    assert stale["awake"] == [] or stale["awake"][0]["wake_reason"] is None


def test_hash_payload_ignores_clock_ticking_fields():
    calls = live.parse_call_lines([_line(0, "architect", "zone.list")])
    a = live.build_live(calls, T0 + 10, public=True)
    b = live.build_live(calls, T0 + 20, public=True)
    assert a != b and live.live_hash_payload(a) == live.live_hash_payload(b)


def test_read_conductor_dir(tmp_path):
    cyc = tmp_path / "cycles" / "cycle-000002-20261005T120000Z"
    cyc.mkdir(parents=True)
    (cyc / "briefings.json").write_text(json.dumps({"architect": {"wake_reason": "ask_open"}}))
    (cyc / "run-architect.json").write_text(json.dumps(
        {"role": "architect", "wall_clock_seconds": 372.0, "cost_usd": 2.5, "ok": True, "timed_out": False}))
    old = tmp_path / "cycles" / "cycle-000001-20261005T110000Z"
    old.mkdir()
    (old / "run-architect.json").write_text(json.dumps({"role": "architect", "wall_clock_seconds": 1.0}))
    (tmp_path / "status.json").write_text(json.dumps({"running": {"role": "x"}}))
    got = live.read_conductor_dir(tmp_path)
    assert got["last_runs"]["architect"]["duration_s"] == 372.0
    assert got["last_runs"]["architect"]["wake_reason"] == "ask_open"
    assert got["running"] == {"role": "x"}
    assert live.read_conductor_dir(None) is None
    assert live.read_conductor_dir(tmp_path / "missing") is None


def test_read_journal_lines_handles_failure_and_success():
    def boom(*a, **k):
        raise FileNotFoundError

    assert live.read_journal_lines(run=boom) is None

    def bad(*a, **k):
        return subprocess.CompletedProcess(a, 1, "", "denied")

    assert live.read_journal_lines(run=bad) is None

    def ok(cmd, **k):
        assert "dfmcp-server.service" in cmd
        return subprocess.CompletedProcess(cmd, 0, "a\nb\n", "")

    assert live.read_journal_lines(run=ok) == ["a", "b"]
