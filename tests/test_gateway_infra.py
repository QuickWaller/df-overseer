"""Offline checks on the openclaw Gateway's committed infra (2026-10-09):
the systemd unit, the config template, the env templates, the manifest wiring
and the secrets hygiene. No host is touched.

What these guard (research/2026-10-09-gateway-sessions-v1.md sections 3, 7, 9):
every proactive feature stays off, the Gateway stays loopback-only with token
auth, the image stays pinned by digest, and nothing address- or secret-shaped
is committed to this public repo.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import deploy_common as dc  # noqa: E402

UNIT = REPO_ROOT / "infra" / "units" / "openclaw" / "openclaw-gateway.service"
CONFIG = REPO_ROOT / "infra" / "openclaw" / "config" / "openclaw.json"
GATEWAY_ENV = REPO_ROOT / "infra" / "openclaw" / "gateway.example.env"
CONDUCTOR_ENV = REPO_ROOT / "infra" / "conductor.example.env"

ROLES = ("architect", "consultant", "overseer", "planner", "quartermaster")


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _unit_lines() -> list:
    return UNIT.read_text(encoding="utf-8").splitlines()


def _exec_start() -> str:
    """ExecStart with its backslash continuations joined."""
    text = UNIT.read_text(encoding="utf-8").replace("\\\n", " ")
    for line in text.splitlines():
        if line.startswith("ExecStart="):
            return re.sub(r"\s+", " ", line)
    raise AssertionError("no ExecStart")


# ---------------------------------------------------------------------------
# config template
# ---------------------------------------------------------------------------


def test_config_is_json_and_every_proactive_feature_is_off():
    c = _config()
    gw = c["gateway"]
    assert gw["mode"] == "local"
    assert gw["bind"] == "loopback"
    assert gw["auth"]["mode"] == "token"
    assert "token" not in gw["auth"], "the token comes from the environment, never the file"
    assert gw["reload"]["mode"] == "off"
    assert gw["controlUi"]["enabled"] is False
    assert gw["terminal"]["enabled"] is False  # gateway.terminal, not a top-level key
    assert c["cron"]["enabled"] is False
    assert c["agents"]["defaults"]["heartbeat"]["every"] == "0m"
    assert c["agents"]["defaults"]["compaction"]["enabled"] is False
    assert c["plugins"]["entries"]["memory-core"]["config"]["dreaming"]["enabled"] is False
    assert c["update"]["checkOnStart"] is False
    assert c["session"]["reset"]["mode"] == "none"


def test_config_configures_no_channels_or_hooks():
    c = _config()
    for key in ("channels", "hooks", "bindings", "talk"):
        assert key not in c, f"{key} must not be configured on the Gateway"


def test_config_charter_delivery_matches_the_context_audit():
    d = _config()["agents"]["defaults"]
    assert d["skipBootstrap"] is True
    assert d["contextInjection"] == "always"  # never "never": that drops SOUL.md


def test_config_has_five_roles_each_limited_to_its_own_mcp_server():
    c = _config()
    assert sorted(c["agents"]["entries"]) == sorted(ROLES)
    assert sorted(c["mcp"]["servers"]) == sorted(f"df-{r}" for r in ROLES)
    for role, entry in c["agents"]["entries"].items():
        assert entry["tools"]["allow"] == [f"df-{role}__*"]
        assert entry["workspace"] == f"/opt/openclaw/gateway/workspaces/{role}"
        server = c["mcp"]["servers"][f"df-{role}"]
        assert server["headers"]["Authorization"] == f"Bearer ${{DF_MCP_TOKEN_{role.upper()}}}"
        assert server["url"] == "${OPENCLAW_MCP_URL}"


def test_config_has_placeholders_only_no_address_or_secret():
    text = CONFIG.read_text(encoding="utf-8")
    assert not re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)
    assert "http://" not in text and "https://" not in text
    # every string value that looks like a credential is a ${ENV} reference
    for ref in re.findall(r"\$\{([^}]*)\}", text):
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", ref), ref
    assert "sk-" not in text


def test_config_deepseek_key_comes_from_the_environment():
    key = _config()["models"]["providers"]["deepseek"]["apiKey"]
    assert key == {"source": "env", "provider": "default", "id": "DEEPSEEK_API_KEY"}


# ---------------------------------------------------------------------------
# unit
# ---------------------------------------------------------------------------


def test_unit_is_loopback_token_auth_and_pinned_by_digest():
    ex = _exec_start()
    assert "--network host" in ex
    assert "--bind loopback" in ex
    assert "--auth token" in ex
    assert "gateway run" in ex
    assert "${OPENCLAW_GATEWAY_IMAGE}" in ex, "the image comes from the env file, pinned by digest there"
    assert ":latest" not in UNIT.read_text(encoding="utf-8")
    # the token is read from a file the container loads, never on a command line
    assert "--token" not in ex and "OPENCLAW_GATEWAY_TOKEN=" not in UNIT.read_text(encoding="utf-8")
    assert "--env-file /opt/openclaw/secrets/gateway-token.env" in ex
    assert "-e OPENCLAW_SKIP_CRON=1" in ex


def test_unit_config_is_read_only_and_state_dir_is_not_the_one_shot_one():
    ex = _exec_start()
    assert "/opt/openclaw/gateway/config/openclaw.json:/home/node/.openclaw/openclaw.json:ro" in ex
    assert "-v /var/lib/openclaw-gateway/state:/home/node/.openclaw" in ex
    # the one-shot runs mount /opt/openclaw/config; a Gateway must never own that directory
    assert "/opt/openclaw/config:" not in ex


def test_unit_supervision_matches_the_design():
    text = UNIT.read_text(encoding="utf-8")
    assert "ExecStop=/usr/bin/docker stop -t 300 openclaw-gateway" in text
    assert "TimeoutStopSec=330" in text
    assert "Restart=on-failure" in text
    assert "RestartPreventExitStatus=78" in text
    assert "ExecStartPre=-/usr/bin/docker rm -f openclaw-gateway" in text
    # session state wiped at every start, so nothing is left for restart recovery to resume
    wipe = [l for l in _unit_lines() if l.startswith("ExecStartPre=") and "-delete" in l]
    assert len(wipe) == 1 and "openclaw-agent.sqlite*" in wipe[0]
    assert "/var/lib/openclaw-gateway/state/agents" in wipe[0]


def test_unit_has_the_conductor_hardening_block_and_is_lf_only():
    text = UNIT.read_text(encoding="utf-8")
    for line in ("NoNewPrivileges=true", "PrivateTmp=true", "ProtectSystem=strict", "ProtectHome=true",
                 "User=df", "SupplementaryGroups=docker"):
        assert line in text
    assert b"\r" not in UNIT.read_bytes()


# ---------------------------------------------------------------------------
# env templates
# ---------------------------------------------------------------------------


def test_env_templates_hold_placeholders_and_no_secret_values():
    for path in (GATEWAY_ENV, CONDUCTOR_ENV):
        text = path.read_text(encoding="utf-8")
        for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
            assert ip in ("127.0.0.1", "0.0.0.0"), f"{path.name}: address {ip}"
        assert not re.search(r"^OPENCLAW_GATEWAY_TOKEN=\S", text, re.M), f"{path.name}: a token value"
        assert not re.search(r"^[A-Z_]*TOKEN[A-Z_]*=[0-9a-f]{16,}", text, re.M)
    g = GATEWAY_ENV.read_text(encoding="utf-8")
    assert re.search(r"^OPENCLAW_GATEWAY_PORT=\d+$", g, re.M)
    assert re.search(r"^OPENCLAW_GATEWAY_IMAGE=\S+@sha256:", g, re.M), "image must be pinned by digest"
    c = CONDUCTOR_ENV.read_text(encoding="utf-8")
    assert re.search(r"^CONDUCTOR_GATEWAY_PORT=\d+$", c, re.M)
    assert re.search(r"^CONDUCTOR_OPENCLAW_IMAGE=\S+@sha256:", c, re.M)


# ---------------------------------------------------------------------------
# manifest wiring
# ---------------------------------------------------------------------------


def test_manifest_vm106_gateway_ships_only_the_config_and_never_restarts_automatically():
    t = dc.load_manifest()["vm106-gateway"]
    assert t.host == "openclaw"
    assert t.destination_root_raw == "/opt/openclaw/gateway"
    assert t.strip_prefix == "infra/openclaw/" and not t.stamp
    files = dc.target_files(t, "HEAD")
    assert files == ["infra/openclaw/config/openclaw.json"]
    assert t.remote_path(files[0]) == "config/openclaw.json"
    assert [(r.service, r.risk) for r in t.restart] == [("openclaw-gateway.service", "high")]
    assert "gateway.env" in t.leave_alone and "workspaces/" in t.leave_alone


def test_manifest_unit_ships_through_vm106_units_and_is_never_enabled_by_deploy():
    t = dc.load_manifest()["vm106-units"]
    assert "infra/units/openclaw/openclaw-gateway.service" in dc.target_files(t, "HEAD")
    risk = {r.service: r.risk for r in t.restart}
    assert risk["openclaw-gateway.service"] == "high"
    assert risk["conductor.service"] == "high"


def test_manifest_dfmcp_deploy_restarts_the_gateway_on_vm106_by_hand():
    t = dc.load_manifest()["vm103-dfmcp"]
    gw = [r for r in t.restart if r.service == "openclaw-gateway.service"]
    assert len(gw) == 1
    assert gw[0].host == "openclaw", "the Gateway lives on VM 106, not the dfmcp host"
    assert gw[0].is_high_risk, "a restart must wait for an idle conductor, so deploy.py never does it"
    assert "drain" in gw[0].why


def test_manifest_gateway_service_is_in_the_drift_check_services_section():
    import drift_check
    targets = dc.load_manifest()
    seen = {}
    runner = dc.FakeRunner({
        ("openclaw", "*"): "ActiveState=inactive\nUnitFileState=disabled\n",
        ("df", "*"): "ActiveState=active\nUnitFileState=enabled\n",
        ("relay", "*"): "ActiveState=active\nUnitFileState=enabled\n",
    })
    seen = drift_check.check_services(targets, runner)
    assert seen["openclaw-gateway.service"]["host"] == "openclaw"


def test_manifest_files_hash_covers_the_config():
    """The config hash drift check is the files check on vm106-gateway: the
    committed bytes at origin/main against the host's sha256."""
    import drift_check
    t = dc.load_manifest()["vm106-gateway"]
    head = dc.current_commit()
    committed = dc.sha256_at_commit(head, "infra/openclaw/config/openclaw.json")
    runner = dc.FakeRunner({("openclaw", "*"): f"{committed}  config/openclaw.json\n"})
    out = drift_check.remote_sha256_many(
        "openclaw", "/opt/openclaw/gateway", ["infra/openclaw/config/openclaw.json"], runner,
        remote_path=t.remote_path,
    )
    assert out == {"infra/openclaw/config/openclaw.json": committed}
