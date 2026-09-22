"""Config for the real conductor service, read from the environment (or a
`.env` merged under it, matching `dfmcp.server.load_config`'s own
convention so this deploy's env file can sit alongside `dfmcp`'s in one
place per host rather than inventing a second style).

No default for anything that names a live host, a real path outside this
checkout, or a secret -- the same "no default that could accidentally be
wrong or public" discipline `dfmcp.server.ServerConfig` already applies
(`bind_host`, `queue_db`). A missing required value is a `ConfigError` at
startup, never a silent fall-through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional

#: The four roles this MVP roster runs (docs/AGENT-LOOP.md §4). The
#: conductor itself is a fifth entry in agents/ROSTER.yaml but is never
#: launched by conductor/runner.py -- it is this service.
ROLES = ("architect", "quartermaster", "consultant", "overseer")

#: docs/AGENT-LOOP.md §4: "Models: DeepSeek for every role." Overridable
#: per role by MCP_ROLE token env below matching, kept as the honest
#: starting default rather than invented per-role variation.
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"


class ConfigError(Exception):
    """A required conductor config value is missing or invalid. Always a
    hard failure at startup, matching dfmcp.server.ConfigError's own
    discipline."""


@dataclass(frozen=True)
class ConductorConfig:
    # dfmcp connection
    mcp_url: str                      # e.g. http://<VM-103-tailnet-addr>:8443/mcp
    mcp_conductor_token: str          # MCP_ROLE_TOKEN_CONDUCTOR -- held ONLY by this service

    # openclaw / docker launch (conductor/runner.py's DockerOpenClawRunner)
    pinned_config_dir: Path           # one <role>.json per role, each with its own systemAgent
    openclaw_state_dir: Path          # bind-mounted at /home/node/.openclaw (persisted auth/plugins)
    workspace_root: Path              # <role>-workspace/ dirs live under here
    secrets_env_file: Path            # --env-file for docker run; never read by this process

    # This service's own local state and archive
    policy_path: Path
    cursor_store_path: Path
    runtime_root: Path                # runtime/cycles, runtime/cost
    status_path: Path

    role_timeout_seconds: float = 600.0
    cycle_interval_seconds: float = 60.0
    models: Mapping[str, str] = field(default_factory=lambda: {r: DEFAULT_MODEL for r in ROLES})


_ENV_KEYS = {
    "mcp_url": "CONDUCTOR_MCP_URL",
    "mcp_conductor_token": "MCP_ROLE_TOKEN_CONDUCTOR",
    "pinned_config_dir": "CONDUCTOR_PINNED_CONFIG_DIR",
    "openclaw_state_dir": "CONDUCTOR_OPENCLAW_STATE_DIR",
    "workspace_root": "CONDUCTOR_WORKSPACE_ROOT",
    "secrets_env_file": "CONDUCTOR_SECRETS_ENV_FILE",
    "policy_path": "CONDUCTOR_POLICY_PATH",
    "cursor_store_path": "CONDUCTOR_CURSOR_STORE_PATH",
    "runtime_root": "CONDUCTOR_RUNTIME_ROOT",
    "status_path": "CONDUCTOR_STATUS_PATH",
    "role_timeout_seconds": "CONDUCTOR_ROLE_TIMEOUT_SECONDS",
    "cycle_interval_seconds": "CONDUCTOR_CYCLE_INTERVAL_SECONDS",
}

_PATH_FIELDS = {
    "pinned_config_dir", "openclaw_state_dir", "workspace_root", "secrets_env_file",
    "policy_path", "cursor_store_path", "runtime_root", "status_path",
}
_FLOAT_FIELDS = {"role_timeout_seconds", "cycle_interval_seconds"}
_REQUIRED_FIELDS = {
    "mcp_url", "mcp_conductor_token", "pinned_config_dir", "openclaw_state_dir",
    "workspace_root", "secrets_env_file", "policy_path", "cursor_store_path",
    "runtime_root", "status_path",
}


def config_from_env(env: Mapping[str, str]) -> ConductorConfig:
    """Pure and dependency-free, matching `dfmcp.server.config_from_env`:
    a test builds this from a plain dict, no file or real environment
    variable required."""
    kwargs: Dict[str, object] = {}
    for field_name, env_key in _ENV_KEYS.items():
        raw = env.get(env_key)
        if raw is None or raw.strip() == "":
            if field_name in _REQUIRED_FIELDS:
                raise ConfigError(f"{env_key} is required and was not set")
            continue
        if field_name in _PATH_FIELDS:
            kwargs[field_name] = Path(raw)
        elif field_name in _FLOAT_FIELDS:
            try:
                kwargs[field_name] = float(raw)
            except ValueError:
                raise ConfigError(f"{env_key}={raw!r} is not a valid number") from None
        else:
            kwargs[field_name] = raw

    # Per-role model override: CONDUCTOR_MODEL_<ROLE> (upper-cased), falling
    # back to DEFAULT_MODEL -- matches docs/AGENT-LOOP.md §4's own default
    # ("DeepSeek for every role") while leaving room to override one role
    # (e.g. the Overseer on a pro-tier model, as every live run so far has).
    models = {}
    for role in ROLES:
        env_key = f"CONDUCTOR_MODEL_{role.upper()}"
        models[role] = env.get(env_key) or DEFAULT_MODEL
    kwargs["models"] = models

    if "role_timeout_seconds" in kwargs and kwargs["role_timeout_seconds"] <= 0:
        raise ConfigError(f"{_ENV_KEYS['role_timeout_seconds']} must be positive")
    if "cycle_interval_seconds" in kwargs and kwargs["cycle_interval_seconds"] <= 0:
        raise ConfigError(f"{_ENV_KEYS['cycle_interval_seconds']} must be positive")

    return ConductorConfig(**kwargs)


def _read_dotenv(path: Path) -> Dict[str, str]:
    """A small, local `KEY=value` reader -- deliberately NOT an import of
    `dfmcp.auth._read_dotenv`: this service runs on VM 106, a different
    host from `dfmcp` (VM 103), and this package otherwise depends on
    nothing from `dfmcp` at all (`conductor/mcp_client.py`'s own docstring
    makes the same host-boundary point about talking to `dfmcp` only over
    the wire). Same shape as every other `.env` reader in this repo: skips
    blank lines and `#` comments, splits on the first `=`, strips
    surrounding whitespace and matching quotes."""
    env: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            env[key] = value
    return env


def load_config(dotenv_path: Optional[Path] = None) -> ConductorConfig:
    """The real entry point's loader: `.env` (if given and present) merged
    under the real process environment, a real env var winning over a
    `.env` entry -- matching `dfmcp.server.load_config`'s own convention,
    without importing across the VM 103/VM 106 host boundary (see
    `_read_dotenv`'s own docstring)."""
    import os

    env: Dict[str, str] = {}
    if dotenv_path is not None and Path(dotenv_path).is_file():
        env.update(_read_dotenv(Path(dotenv_path)))
    env.update(os.environ)
    return config_from_env(env)
