"""Offline tests for scripts/drift_check_telegram_alert.py. Never a real
HTTP call, never a real ssh call."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import deploy_common as dc  # noqa: E402
import drift_check_telegram_alert as alert  # noqa: E402


def test_read_telegram_credentials_requires_both(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=abc\n", encoding="utf-8")
    assert alert.read_telegram_credentials(env_path) is None

    env_path.write_text("TELEGRAM_BOT_TOKEN=abc\nUSER_TELEGRAM_ID=123\n", encoding="utf-8")
    assert alert.read_telegram_credentials(env_path) == ("abc", "123")


def test_format_message_lists_drifted_targets_only():
    report = {
        "generated_at": "2026-10-02T00:00:00Z",
        "clean": False,
        "files": {
            "clean-target": {"clean": True, "drifted_count": 0, "file_count": 5},
            "bad-target": {"clean": False, "drifted_count": 2, "file_count": 5},
        },
        "live_tool_counts": {"clean": True, "mismatches": {}},
        "website": {"files": None, "generated_json": {"clean": True}},
    }
    message = alert.format_message(report)
    assert "bad-target: 2/5" in message
    assert "clean-target" not in message


def test_dry_run_never_sends_and_prints_message(monkeypatch, capsys):
    def fail_if_called(*a, **kw):
        raise AssertionError("send_telegram_message must not be called in --dry-run")
    monkeypatch.setattr(alert, "send_telegram_message", fail_if_called)

    head = dc.current_commit()
    real_hash = dc.sha256_at_commit(head, "agents/ROSTER.yaml")
    runner = dc.FakeRunner({
        ("df", "cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): "",
        ("df", "cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"):
            f"{'f' * 64}  agents/ROSTER.yaml\n",  # deliberately wrong hash -> drift
        ("df", "test -f /opt/sample/scripts/ops/mcpcall.py && echo present || echo absent"): "absent\n",
    })
    targets = {
        "sample": dc.Target(name="sample", host="df", destination_root_raw="/opt/sample",
                             paths=["agents/ROSTER.yaml"]),
    }
    monkeypatch.setattr(dc, "load_manifest", lambda path=dc.MANIFEST_PATH: targets)
    monkeypatch.setattr(dc, "SSHRunner", lambda env_file=None: runner)

    rc = alert.main(["--dry-run"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "DRIFT found" in out
    assert "sample" in out


def test_unreachable_host_alerts_instead_of_crashing_dry_run(monkeypatch, capsys):
    """An SSHError (host down, network unreachable) must still produce an
    alert message, not an uncaught traceback with nothing sent."""
    def raising_run(host, command, input_bytes=None):
        raise dc.SSHError("vm-ssh.sh df failed (exit 255): ssh: connect to host port 22: timed out")
    runner = dc.FakeRunner()
    monkeypatch.setattr(runner, "run", raising_run)
    targets = {
        "sample": dc.Target(name="sample", host="df", destination_root_raw="/opt/sample",
                             paths=["agents/ROSTER.yaml"]),
    }
    monkeypatch.setattr(dc, "load_manifest", lambda path=dc.MANIFEST_PATH: targets)
    monkeypatch.setattr(dc, "SSHRunner", lambda env_file=None: runner)

    rc = alert.main(["--dry-run"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "timed out" in out


def test_unreachable_host_alerts_for_real_when_not_dry_run(monkeypatch, tmp_path):
    def raising_run(host, command, input_bytes=None):
        raise dc.SSHError("vm-ssh.sh df failed (exit 255): unreachable")
    runner = dc.FakeRunner()
    monkeypatch.setattr(runner, "run", raising_run)
    targets = {
        "sample": dc.Target(name="sample", host="df", destination_root_raw="/opt/sample",
                             paths=["agents/ROSTER.yaml"]),
    }
    monkeypatch.setattr(dc, "load_manifest", lambda path=dc.MANIFEST_PATH: targets)
    monkeypatch.setattr(dc, "SSHRunner", lambda env_file=None: runner)

    sent = {}
    def fake_send(token, chat_id, text):
        sent["token"] = token
        sent["chat_id"] = chat_id
        sent["text"] = text
    monkeypatch.setattr(alert, "send_telegram_message", fake_send)

    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=abc\nUSER_TELEGRAM_ID=123\n", encoding="utf-8")

    rc = alert.main(["--env-file", str(env_path)])
    assert rc == 1
    assert "ERROR" in sent["text"]
    assert sent["token"] == "abc"
    assert sent["chat_id"] == "123"


def test_main_clean_report_returns_zero_without_formatting(monkeypatch):
    head = dc.current_commit()
    real_hash = dc.sha256_at_commit(head, "agents/ROSTER.yaml")
    runner = dc.FakeRunner({
        ("df", f"cat /opt/sample/DEPLOYED_COMMIT 2>/dev/null || true"): f"commit={head}\n",
        ("df", "cd /opt/sample && sha256sum agents/ROSTER.yaml 2>&1 || true"):
            f"{real_hash}  agents/ROSTER.yaml\n",
        ("df", "test -f /opt/sample/scripts/ops/mcpcall.py && echo present || echo absent"): "absent\n",
    })
    targets = {
        "sample": dc.Target(name="sample", host="df", destination_root_raw="/opt/sample",
                             paths=["agents/ROSTER.yaml"]),
    }
    monkeypatch.setattr(dc, "load_manifest", lambda path=dc.MANIFEST_PATH: targets)
    monkeypatch.setattr(dc, "SSHRunner", lambda env_file=None: runner)

    rc = alert.main([])
    assert rc == 0
