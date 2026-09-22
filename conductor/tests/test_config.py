"""conductor/config.py: env-based config, no dangerous defaults, per-role
model override."""

from __future__ import annotations

import pytest

from pathlib import Path

from conductor.config import DEFAULT_MODEL, ROLES, ConfigError, config_from_env, load_config

_REQUIRED_ENV = {
    "CONDUCTOR_MCP_URL": "http://127.0.0.1:8443/mcp",
    "MCP_ROLE_TOKEN_CONDUCTOR": "not-a-real-token",
    "CONDUCTOR_PINNED_CONFIG_DIR": "/opt/conductor/config",
    "CONDUCTOR_OPENCLAW_STATE_DIR": "/opt/openclaw/config",
    "CONDUCTOR_WORKSPACE_ROOT": "/opt/openclaw",
    "CONDUCTOR_SECRETS_ENV_FILE": "/opt/openclaw/secrets/openclaw_secrets.env",
    "CONDUCTOR_POLICY_PATH": "/opt/conductor/policy.yaml",
    "CONDUCTOR_CURSOR_STORE_PATH": "/var/lib/conductor/cursors.json",
    "CONDUCTOR_RUNTIME_ROOT": "/var/lib/conductor/runtime",
    "CONDUCTOR_STATUS_PATH": "/var/lib/conductor/status.json",
}


def test_config_from_env_builds_a_valid_config():
    config = config_from_env(_REQUIRED_ENV)
    assert config.mcp_url == "http://127.0.0.1:8443/mcp"
    assert config.mcp_conductor_token == "not-a-real-token"
    assert config.pinned_config_dir == Path("/opt/conductor/config")
    assert config.role_timeout_seconds == 600.0
    assert config.cycle_interval_seconds == 60.0


def test_every_role_gets_the_default_model_unless_overridden():
    config = config_from_env(_REQUIRED_ENV)
    for role in ROLES:
        assert config.models[role] == DEFAULT_MODEL


def test_a_per_role_model_override_is_honoured():
    env = dict(_REQUIRED_ENV, CONDUCTOR_MODEL_OVERSEER="deepseek/deepseek-v4-pro")
    config = config_from_env(env)
    assert config.models["overseer"] == "deepseek/deepseek-v4-pro"
    assert config.models["architect"] == DEFAULT_MODEL


@pytest.mark.parametrize("missing_key", sorted(_REQUIRED_ENV))
def test_a_missing_required_key_is_refused(missing_key):
    env = dict(_REQUIRED_ENV)
    del env[missing_key]
    with pytest.raises(ConfigError, match=missing_key):
        config_from_env(env)


def test_a_non_numeric_timeout_is_refused():
    env = dict(_REQUIRED_ENV, CONDUCTOR_ROLE_TIMEOUT_SECONDS="not-a-number")
    with pytest.raises(ConfigError):
        config_from_env(env)


def test_a_negative_timeout_is_refused():
    env = dict(_REQUIRED_ENV, CONDUCTOR_ROLE_TIMEOUT_SECONDS="-5")
    with pytest.raises(ConfigError):
        config_from_env(env)


def test_load_config_merges_a_dotenv_file_under_the_real_environment(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    lines = "\n".join(f"{k}={v}" for k, v in _REQUIRED_ENV.items())
    dotenv.write_text(lines, encoding="utf-8")

    for key in _REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    # A real env var wins over the .env entry.
    monkeypatch.setenv("CONDUCTOR_MCP_URL", "http://real-env-wins/mcp")

    config = load_config(dotenv)
    assert config.mcp_url == "http://real-env-wins/mcp"
    assert config.mcp_conductor_token == "not-a-real-token"  # came from the .env file


def test_load_config_with_no_dotenv_file_falls_through_to_the_real_environment(tmp_path, monkeypatch):
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    config = load_config(tmp_path / "does-not-exist.env")
    assert config.mcp_url == _REQUIRED_ENV["CONDUCTOR_MCP_URL"]
