"""The stream page's real publisher (slice S1,
`handoffs/2026-10-01-stream-page-s1-prep.md` task 1). Runs on VM 103 under
systemd (`infra/stream-publisher.service.example` +
`infra/stream-publisher.timer.example`, both UNDEPLOYED templates, same
"review before running" convention as every other `infra/*.example` file),
reads the live queue read-only exactly as `scripts/export_stream_feed.py`
reads a static export, and pushes the built `data/public/` and
`data/operator/` layout outward to the relay over `rsync`/`ssh` using a key
restricted to one directory there (design
`research/2026-10-01-stream-page-design.md` §4.1: "VM 103 only dials out").

Each side's staged/pushed directory is now the multi-fort projection root
`dfqueue.feed.write_fort_feed` writes (register 2026-10-02, "plan for more
than one fort"): `forts.json` plus `forts/<fort-id>/...`, the same layout
`scripts/export_stream_feed.py` writes, not the old flat `head.json`-at-root
shape. `--fort-id` (`STREAM_PUBLISHER_FORT_ID`) defaults to the `--db`
file's own stem (`/var/lib/dfqueue/Uniboslan.sqlite3` -> `Uniboslan`);
`--fort-name`/`--fort-status` (`STREAM_PUBLISHER_FORT_NAME`/
`STREAM_PUBLISHER_FORT_STATUS`) default to `Ragwind`/`live`. **The first
deploy of this change makes the relay's existing flat paths
(`.../data/public/head.json` etc, if anything was ever pushed there before)
stale** -- `web/stream/app.js` falls back to treating the projection root as
one flat fort's feed only when `forts.json` is entirely absent, so a stale
flat `head.json` left over from before this change, sitting ALONGSIDE a new
`forts.json`, is just inert: the page reads `forts.json` and follows
whichever fort is `current`, never the old flat files once that index
exists. Nothing needs manual cleanup on the relay, though removing the old
flat files there is harmless if wanted.

Usage (local staging only, no push -- for review)::

    python scripts/stream_publisher.py --once \\
        --db dfqueue/Uniboslan.sqlite3 --staging-dir /tmp/stream-stage

Usage (real push, once a relay and a restricted key exist)::

    python scripts/stream_publisher.py --once \\
        --db /var/lib/dfqueue/Uniboslan.sqlite3 \\
        --staging-dir /var/lib/stream-publisher/stage \\
        --kill-switch-file /var/lib/stream-publisher/STOP \\
        --public-relay-host <relay-vm-ip> --public-relay-user stream-pub \\
        --public-relay-path /srv/stream/data/public \\
        --public-relay-ssh-key /etc/stream-publisher/relay_push_ed25519 \\
        --operator-relay-host <relay-vm-ip> --operator-relay-user stream-pub \\
        --operator-relay-path /srv/stream/data/operator \\
        --operator-relay-ssh-key /etc/stream-publisher/relay_push_ed25519

Every flag has an environment-variable equivalent (`STREAM_PUBLISHER_*`,
see `config_from_env` / `infra/stream-publisher.example.env`), read the same
way `dfmcp/server.py`'s `ServerConfig`/`config_from_env` are: a real
environment variable wins over `.env`, which wins over nothing. No flag or
variable needs a committed real value -- every example below uses a
placeholder, per this repo's "no hosts, addresses, keys or remote paths in
a committed file" rule.

## What this script does NOT do

- **Never writes to the queue.** `dfqueue.feed.load_records_readonly` and
  `dfqueue.feed_status`'s own functions both open the database with SQLite's
  `file:...?mode=ro` URI mode, never `dfqueue.store._connect` (which runs
  `_ensure_schema`, a write, on open). This module imports no write
  function from either `dfqueue.store` or `dfqueue.schema` at all --
  `test_stream_publisher.py::test_module_imports_no_queue_write_path` pins
  that down statically, and a second test runs a full cycle against a
  database file made read-only on disk (`os.chmod`, not just the SQLite URI)
  to prove it end to end.
- **Never builds the real safety layers 3/4** (design §7.2's write-time
  field refusal, which belongs in `dfqueue/schema.py`, and the publish-time
  canary against the estate's real secrets, which needs a gitignored
  `infra/local.*` list this repo does not ship). This script relies entirely
  on the withhold net `dfqueue.feed` already applies inside
  `feed.build_public_item` (`feed.find_unsafe_pattern`) -- real, but
  deliberately not the full design.
- **Never deploys itself.** `infra/stream-publisher.service.example` and
  `infra/stream-publisher.timer.example` are reviewed-not-run templates,
  same convention as `infra/dfmcp-server.service.example`'s own header.
  This handoff is explicitly "build and test everything S1 needs, deploy
  nothing" -- the orchestrator runs the real install after the user's
  go-ahead, per `web/stream/README.md`'s runbook section.

## Kill switches (design §4.6, this handoff's task 1)

Two independent switches, checked every cycle, in order:

1. **`--kill-switch-file`**: if the file exists, NOTHING is pushed to the
   relay this cycle, public or operator -- the loudest, simplest "stop
   everything" switch, a `touch`/`rm` away on VM 103 alone, matching the
   handoff's literal wording ("a kill switch file that stops all
   publishing"). Local staging files are still written (harmless, and lets
   an operator inspect what *would* have been pushed), only the push itself
   is skipped.
2. **`--public-disabled` / `STREAM_PUBLISHER_PUBLIC_ENABLED=false`** (design
   §4.6 layer 2): only the PUBLIC side stops. `data/public/head.json` is
   written and pushed as `{"state": "off"}` with every segment removed
   (`rsync --delete`); the operator side keeps running untouched. This is
   the slower, deliberate switch meant to be flipped from a config change,
   not an emergency `touch`.

Neither switch is reachable by any role's tool allowlist -- both are files
and flags this script alone reads, matching design §4.6's "no agent can
reach any of the three" (the third, a Cloudflare rule, is dashboard-only and
out of this script's scope entirely).

## Change detection and restart safety (design §4.1, §4.5)

Every cycle rebuilds the full projection from the queue from scratch --
cheap at this fort's real record counts (design §4.7's own year-one
estimate is at most on the order of a million records; this slice has seen
dozens) -- and computes a content hash over the built items/projects/status
*before* any wall-clock timestamp is attached (`compute_content_hash`,
which never sees `published_at`). Only when that hash changes from the
previous cycle's (kept in a small JSON cursor file beside the staging
directory) does it push, except a heartbeat push at least every
`--heartbeat-interval` seconds even with no change, so a quiet fort's
`head.json.published_at` still proves the publisher is alive (design §4.5:
the page needs that timestamp moving to tell "quiet" from "stale"). Losing
the cursor file costs one extra push of identical content, never data
(design §4.5's own "full rebuild; identical bytes, so no churn").

## Step-level project progress (this handoff's other named task-1 item)

`dfqueue/feed.py`'s own `GAPS` list named this: `feed.build_projects_view`
alone cannot report per-step counts or a held target's blocker, because
`dfqueue.store.project_status` reads through the write-capable `_connect`.
`dfqueue/feed_status.py` (this same handoff) closes that gap read-only; this
script is `feed_status`'s first real caller, merging `counts` into every
project (safe on both projections -- a bare state-name tally) and
`top_blocker` into the operator projection only (a held target's `reason`
is free text written by a tool, not for an audience -- design §3.3 item 7's
"the free-text reason stays, operator only," until hold codes exist in
slice S4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dfqueue import feed, feed_status, live, site_data  # noqa: E402  (path setup must run first)

DEFAULT_ENV_PATH = REPO_ROOT / ".env"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60
DEFAULT_LOOP_INTERVAL_SECONDS = 5
CURSOR_FILENAME = ".publisher-cursor.json"
# Same default `scripts/export_stream_feed.py --fort-name` uses -- the one
# real fort this repo automates today (CLAUDE.md's own "Current state").
DEFAULT_FORT_NAME = "Ragwind"
_VALID_FORT_STATUSES = ("live", "lost")


class ConfigError(Exception):
    """Raised by `config_from_env`/`load_config` for a missing or invalid
    setting -- same role `dfmcp.server.ConfigError` plays for the MCP
    server, deliberately not shared across the two (this script has no
    dependency on `dfmcp` at all)."""


# ---- config -------------------------------------------------------------


@dataclass(frozen=True)
class RelayTarget:
    """One rsync destination: pushed to as `user@host:path` using
    `ssh_key` -- the directory-restricted key design §4.1 requires
    (`infra/stream-publisher-authorized-keys-line.example` is the template
    for the relay-side half of that restriction)."""

    host: str
    user: str
    path: str
    ssh_key: str

    def destination(self) -> str:
        return f"{self.user}@{self.host}:{self.path}"


@dataclass
class PublisherConfig:
    """`db_path`/`staging_dir` default to `""` rather than being required
    dataclass fields, deliberately: the CLI builds a config in two steps
    (environment/`.env` first, then flag overrides on top), and a strict
    `__post_init__` would reject the intermediate, env-only object before
    the flags ever get a chance to fill in what `.env` left blank. Call
    `validate()` once the config is as complete as it will ever get --
    `config_from_env`/`load_config` do this by default (`validate=True`),
    and `main()` does it explicitly after merging CLI flags on top."""

    db_path: str = ""
    staging_dir: str = ""
    public_relay: Optional[RelayTarget] = None
    operator_relay: Optional[RelayTarget] = None
    kill_switch_file: Optional[str] = None
    public_enabled: bool = True
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    loop_interval_seconds: int = DEFAULT_LOOP_INTERVAL_SECONDS
    rsync_bin: str = "rsync"
    fort_id: str = ""
    fort_name: str = DEFAULT_FORT_NAME
    fort_status: str = "live"
    # Project-wide data (agents.json/tools.json/gotchas.json,
    # `dfqueue.site_data`), not any one fort's -- `None` is an honest
    # "no gotcha store configured" state, same shape `db_path`'s own
    # absence-is-an-error convention would otherwise suggest, except this
    # one is optional: an export with no gotchas store still publishes the
    # roster and tool catalog, just with an empty gotchas.json.
    gotchas_db: Optional[str] = None
    # The "who is awake" live view (handoffs/2026-10-05-board-order-year-
    # live-view.md): read `dfmcp-server`'s call journal on this host, and/or
    # a local copy of the conductor's runtime root. Both off by default, so
    # the status.json stays the plain placeholder until a deploy turns them on.
    live_journal: bool = False
    conductor_dir: Optional[str] = None
    # The conductor's run reports (handoffs/2026-10-05-conductor-report.md):
    # `dfqueue/runs.py`'s store. Default: `<db stem>.runs.sqlite3` beside the
    # queue database, used only if that file exists (see `resolved_runs_db`).
    runs_db: Optional[str] = None

    def resolved_runs_db(self) -> Optional[str]:
        if self.runs_db:
            return self.runs_db
        if not self.db_path:
            return None
        from dfqueue import runs as runs_store
        candidate = runs_store.runs_path(self.db_path)
        return str(candidate) if candidate.is_file() else None

    def resolved_fort_id(self) -> str:
        """`fort_id` when explicitly configured, else the queue file's own
        stem (`/var/lib/dfqueue/Uniboslan.sqlite3` -> `Uniboslan`) -- the
        same convention `scripts/export_stream_feed.py`'s own
        `_default_fort_id` uses for a `--db` export, never a guess at a
        SECOND fort's name."""
        return self.fort_id or Path(self.db_path).stem

    def validate(self) -> None:
        if not self.db_path or not str(self.db_path).strip():
            raise ConfigError(
                "db_path must be set explicitly -- STREAM_PUBLISHER_DB or --db. "
                "There is no in-tree default, same reason dfmcp.server.ServerConfig "
                "gives none for queue_db: a code redeploy must never resolve a "
                "relative path onto live queue data."
            )
        if not self.staging_dir or not str(self.staging_dir).strip():
            raise ConfigError(
                "staging_dir must be set explicitly -- STREAM_PUBLISHER_STAGING_DIR "
                "or --staging-dir."
            )
        if self.heartbeat_interval_seconds < 1:
            raise ConfigError("heartbeat_interval_seconds must be at least 1")
        if self.loop_interval_seconds < 1:
            raise ConfigError("loop_interval_seconds must be at least 1")
        if self.fort_status not in _VALID_FORT_STATUSES:
            raise ConfigError(
                f"fort_status={self.fort_status!r} must be one of {_VALID_FORT_STATUSES}"
            )


_RELAY_FIELDS = ("host", "user", "path", "ssh_key")


def _relay_from_env(env: Mapping[str, str], prefix: str) -> Optional[RelayTarget]:
    """Build a `RelayTarget` from `STREAM_PUBLISHER_<PREFIX>_RELAY_{HOST,
    USER,PATH,SSH_KEY}`, or `None` if none of the four are set at all (the
    "write locally only, push to nowhere" mode this handoff's own offline
    scope needs for review and tests). Raises `ConfigError` if only SOME of
    the four are set -- a half-configured relay is a misconfiguration, never
    silently partial."""
    keys = {f: f"STREAM_PUBLISHER_{prefix}_RELAY_{f.upper()}" for f in _RELAY_FIELDS}
    values = {f: env.get(k) for f, k in keys.items()}
    present = {f: v for f, v in values.items() if v}
    if not present:
        return None
    if len(present) != len(_RELAY_FIELDS):
        missing = [keys[f] for f in _RELAY_FIELDS if f not in present]
        raise ConfigError(
            f"{prefix} relay is partially configured -- missing: {', '.join(missing)}"
        )
    return RelayTarget(**values)  # type: ignore[arg-type]


def _parse_bool(raw: str, env_key: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{env_key}={raw!r} is not a valid boolean")


def config_from_env(env: Mapping[str, str], *, validate: bool = True) -> PublisherConfig:
    """Build a `PublisherConfig` from a plain `{name: value}` mapping (e.g.
    `os.environ`, or a dict merged from `.env`) -- pure, so tests exercise it
    with a plain dict, no file or real environment variable required. Same
    shape as `dfmcp.server.config_from_env`. `validate=False` (used by the
    CLI's two-step build, `_config_from_args`) skips the `db_path`/
    `staging_dir` presence check so flag overrides can still fill them in."""
    kwargs: dict[str, Any] = {}
    if env.get("STREAM_PUBLISHER_DB"):
        kwargs["db_path"] = env["STREAM_PUBLISHER_DB"]
    if env.get("STREAM_PUBLISHER_STAGING_DIR"):
        kwargs["staging_dir"] = env["STREAM_PUBLISHER_STAGING_DIR"]
    if env.get("STREAM_PUBLISHER_KILL_SWITCH_FILE"):
        kwargs["kill_switch_file"] = env["STREAM_PUBLISHER_KILL_SWITCH_FILE"]
    if env.get("STREAM_PUBLISHER_PUBLIC_ENABLED"):
        kwargs["public_enabled"] = _parse_bool(
            env["STREAM_PUBLISHER_PUBLIC_ENABLED"], "STREAM_PUBLISHER_PUBLIC_ENABLED"
        )
    if env.get("STREAM_PUBLISHER_HEARTBEAT_SECONDS"):
        kwargs["heartbeat_interval_seconds"] = int(env["STREAM_PUBLISHER_HEARTBEAT_SECONDS"])
    if env.get("STREAM_PUBLISHER_LOOP_SECONDS"):
        kwargs["loop_interval_seconds"] = int(env["STREAM_PUBLISHER_LOOP_SECONDS"])
    if env.get("STREAM_PUBLISHER_RSYNC_BIN"):
        kwargs["rsync_bin"] = env["STREAM_PUBLISHER_RSYNC_BIN"]
    if env.get("STREAM_PUBLISHER_FORT_ID"):
        kwargs["fort_id"] = env["STREAM_PUBLISHER_FORT_ID"]
    if env.get("STREAM_PUBLISHER_FORT_NAME"):
        kwargs["fort_name"] = env["STREAM_PUBLISHER_FORT_NAME"]
    if env.get("STREAM_PUBLISHER_FORT_STATUS"):
        kwargs["fort_status"] = env["STREAM_PUBLISHER_FORT_STATUS"]
    if env.get("STREAM_PUBLISHER_GOTCHAS_DB"):
        kwargs["gotchas_db"] = env["STREAM_PUBLISHER_GOTCHAS_DB"]

    if env.get("STREAM_PUBLISHER_LIVE_JOURNAL"):
        kwargs["live_journal"] = _parse_bool(
            env["STREAM_PUBLISHER_LIVE_JOURNAL"], "STREAM_PUBLISHER_LIVE_JOURNAL"
        )
    if env.get("STREAM_PUBLISHER_CONDUCTOR_DIR"):
        kwargs["conductor_dir"] = env["STREAM_PUBLISHER_CONDUCTOR_DIR"]
    if env.get("STREAM_PUBLISHER_RUNS_DB"):
        kwargs["runs_db"] = env["STREAM_PUBLISHER_RUNS_DB"]

    public_relay = _relay_from_env(env, "PUBLIC")
    operator_relay = _relay_from_env(env, "OPERATOR")
    if public_relay is not None:
        kwargs["public_relay"] = public_relay
    if operator_relay is not None:
        kwargs["operator_relay"] = operator_relay

    cfg = PublisherConfig(**kwargs)
    if validate:
        cfg.validate()
    return cfg


def _read_dotenv(path: Path) -> dict[str, str]:
    """Same quoting rules as `scripts/pve.py`'s `load_env` (handles a
    single- or double-quoted value) -- duplicated rather than imported
    because `scripts/pve.py` is a standalone CLI, not a library this script
    should depend on."""
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env[key.strip()] = value
    return env


def load_config(env_path: Path = DEFAULT_ENV_PATH, *, validate: bool = True) -> PublisherConfig:
    """Real entry point's config: `.env` merged under the real process
    environment (a real env var wins over a `.env` entry)."""
    env = _read_dotenv(env_path)
    env.update(os.environ)
    return config_from_env(env, validate=validate)


# ---- content hashing (design §4.1's "same records, same bytes") ------------


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=None)


def compute_content_hash(
    items: list, projects: dict, status: Optional[dict], site: Optional[dict] = None,
) -> str:
    """A hash over exactly what changes the reader's experience -- never a
    wall-clock field. Two cycles that would write byte-identical
    `head.json`/`open.json`/`projects.json` (ignoring `published_at`)
    produce the same hash, which is what lets `run_cycle` tell "nothing
    changed" from "something changed" without diffing files on disk. `site`
    (agents.json/tools.json/gotchas.json, added for the Agents/Tools/Forts
    stream) folds project-wide data into the same change-detection path, so
    an allowlist or confidence-level edit triggers a push exactly like a new
    chat item would -- optional and defaulted to `None` so every existing
    caller (and the hash this produces for it) is unchanged."""
    body = _canonical_json({"items": items, "projects": projects, "status": status, "site": site})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---- the step-progress merge (this handoff's feed_status gap) --------------


def _merge_project_progress(
    projects_view: dict, project_statuses: dict[str, dict], *, public: bool,
) -> None:
    """Add `counts` (both projections -- a bare tally of step-target state
    names, safe either way) and, operator only, `top_blocker` (a held
    target's free-text `reason`, never public until design §3.3 item 7's
    hold codes exist) to every project `feed.build_projects_view` already
    produced. Mutates `projects_view["projects"]` in place; a project id
    `feed_status` has no status for (should not happen -- both read the same
    records -- but never assumed) is left exactly as `feed` built it."""
    for pid, entry in projects_view["projects"].items():
        status = project_statuses.get(pid)
        if status is None:
            continue
        entry["counts"] = status["counts"]
        if not public:
            entry["top_blocker"] = status["top_blocker"]


def build_projection(
    records: list[dict], *, public: bool, project_statuses: dict[str, dict],
) -> tuple[list[dict], dict]:
    """One projection (public or operator): `feed.build_items` plus
    `feed.build_projects_view`, with step-level progress merged in from
    `feed_status` (read-only, this handoff's other task-1 deliverable)."""
    items = feed.build_items(records, public=public)
    projects_view = feed.build_projects_view(records, public=public)
    _merge_project_progress(projects_view, project_statuses, public=public)
    return items, projects_view


# ---- the cursor file (design §4.5's restart safety) ------------------------


def _read_cursor(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt or unreadable cursor costs one extra push of identical
        # content (design §4.5), never a crash -- treat it as "no cursor".
        return {}


def _write_cursor(path: Path, cursor: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(cursor), encoding="utf-8")


# ---- the push itself (the only function a test ever has to replace) --------


def _rsync_push(
    local_dir: Path, relay: RelayTarget, *, delete: bool = False, rsync_bin: str = "rsync",
) -> subprocess.CompletedProcess:
    """Push `local_dir`'s contents into `relay.path` over SSH, using
    `relay.ssh_key` -- design §4.1's directory-restricted key, never the
    operator's own login key. `BatchMode=yes` so a bad or missing key fails
    loudly instead of hanging on a password prompt (this runs unattended
    under systemd); `StrictHostKeyChecking=accept-new` so a first run does
    not block on an interactive host-key prompt either, while still
    refusing a host whose key later CHANGES (never `=no`, which would accept
    a changed key silently too).

    Trailing slash on the source, none on the destination: rsync's own
    "copy contents of this directory into that one" convention, not "copy
    this directory as a subdirectory of that one"."""
    cmd = [
        rsync_bin, "-az",
        "-e", f"ssh -i {relay.ssh_key} -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
    ]
    if delete:
        cmd.append("--delete")
    cmd += [f"{local_dir}{os.sep}", relay.destination().rstrip("/") + "/"]
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


Pusher = Callable[..., Any]


def _site_hash_payload(agents_json: dict, tools_json: dict, gotchas: list) -> dict:
    """`agents_json`/`tools_json` minus their own `generated_at` -- a
    wall-clock field that would otherwise bust `compute_content_hash` every
    single cycle even when nothing about the roster, tools or gotchas
    actually changed (the exact trap `compute_content_hash`'s own docstring
    warns about for `published_at`)."""
    agents_stable = {k: v for k, v in agents_json.items() if k != "generated_at"}
    tools_stable = {k: v for k, v in tools_json.items() if k != "generated_at"}
    return {"agents": agents_stable, "tools": tools_stable, "gotchas": gotchas}


def _with_runs(site: dict, runs_payload: Optional[dict]) -> dict:
    """Folds the run reports into the change-detection payload (minus their
    wall-clock `as_of`), only when a run store exists, so a fort without one
    hashes exactly as before."""
    if runs_payload is None:
        return site
    return {**site, "runs": live.live_hash_payload(runs_payload)}


def _write_runs(out_root: Path, fort_id: str, runs_payload: Optional[dict]) -> None:
    """`<root>/forts/<fort_id>/runs.json`, next to that fort's `head.json`.
    Nothing is written (and a stale file is left to the next successful
    cycle) when there is no run store."""
    if runs_payload is None:
        return
    target = feed.fort_feed_dir(out_root, fort_id) / "runs.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_canonical_json(runs_payload), encoding="utf-8")


# ---- one cycle --------------------------------------------------------------


def run_cycle(
    cfg: PublisherConfig, *, now: Optional[float] = None, pusher: Optional[Pusher] = None,
    journal_reader: Optional[Callable[[], Optional[list]]] = None,
) -> dict[str, Any]:
    """Build both projections from the live queue, write them to
    `cfg.staging_dir`, and push whichever side needs pushing. Returns a
    small JSON-able summary (`{"public": {...}, "operator": {...}}`) meant
    to be printed and captured by journald under the real systemd unit --
    never raises on a disabled or unreachable relay, only on something the
    cycle itself could not recover from (a missing/unreadable database, a
    real rsync failure, which `subprocess.run(check=True)` turns into a
    `CalledProcessError`)."""
    now = time.time() if now is None else now
    pusher = _rsync_push if pusher is None else pusher

    kill_switch_active = bool(cfg.kill_switch_file) and Path(cfg.kill_switch_file).is_file()

    records = feed.load_records_readonly(cfg.db_path)
    project_statuses = feed_status.all_project_statuses_readonly(cfg.db_path)

    public_items, public_projects = build_projection(
        records, public=True, project_statuses=project_statuses
    )
    operator_items, operator_projects = build_projection(
        records, public=False, project_statuses=project_statuses
    )
    # design §3.1 GAP: feed.status (a live per-cycle status push) is not
    # built -- no conductor-side writer exists yet (slice S2). This is the
    # only status.json this script can honestly produce, same as
    # scripts/export_stream_feed.py.
    status = feed.build_placeholder_status()
    live_public = live_operator = None
    # The conductor's run reports, read-only and optional: absent store gives
    # None, which changes nothing below (no runs.json, no `+reports` source).
    run_rows = live.read_runs(cfg.resolved_runs_db())
    lines = None
    if cfg.live_journal or cfg.conductor_dir or run_rows is not None:
        lines = (journal_reader or live.read_journal_lines)() if cfg.live_journal else []
    calls = None if lines is None else live.parse_call_lines(lines)
    record_ts = {r.get("id"): r.get("ts") for r in records if isinstance(r, dict)}
    # `write`/`description` per tool, the public tools.json's own text
    # (built again below for the site files; cheap and read-only).
    tools_info = {t["id"]: t for t in site_data.build_tools_json()["tools"]} if run_rows else None
    runs_public = live.build_runs(run_rows, now, public=True, calls=calls, tools=tools_info, record_ts=record_ts)
    runs_operator = live.build_runs(run_rows, now, public=False, calls=calls, tools=tools_info, record_ts=record_ts)
    if cfg.live_journal or cfg.conductor_dir or run_rows is not None:
        conductor = live.read_conductor_dir(cfg.conductor_dir)
        live_public = live.build_live(calls, now, public=True, conductor=conductor, runs=run_rows)
        live_operator = live.build_live(calls, now, public=False, conductor=conductor, runs=run_rows)
    status_public = status if live_public is None else {**status, "live": live_public}
    status_operator = status if live_operator is None else {**status, "live": live_operator}
    # The hash sees `live` without its clock-ticking fields (live.live_hash_payload).
    hash_status_public = status if live_public is None else {**status, "live": live.live_hash_payload(live_public)}
    hash_status_operator = status if live_operator is None else {**status, "live": live.live_hash_payload(live_operator)}

    # Project-wide data (handoffs/2026-10-02-site-agents-tools.md): the same
    # across every fort, read fresh each cycle like everything else here
    # (dfqueue.site_data's own read-only guarantees: the roster/registry
    # loader never writes, and the gotcha store is opened `mode=ro`, same
    # discipline as `feed.load_records_readonly` above).
    agents_json = site_data.build_agents_json(records)
    tools_json = site_data.build_tools_json()
    gotchas_entries = (
        site_data.load_gotchas_readonly(cfg.gotchas_db) if cfg.gotchas_db else []
    )
    public_gotchas = site_data.build_gotchas_json(gotchas_entries, public=True)
    operator_gotchas = site_data.build_gotchas_json(gotchas_entries, public=False)

    fort_id = cfg.resolved_fort_id()
    staging = Path(cfg.staging_dir)
    cursor_path = staging / CURSOR_FILENAME
    cursor = _read_cursor(cursor_path)

    result: dict[str, Any] = {
        "kill_switch_active": kill_switch_active,
        "public": {"pushed": False, "reason": None},
        "operator": {"pushed": False, "reason": None},
    }

    # ---- operator side: never disabled by public_enabled, only by the
    # kill-switch file or having no relay configured at all. ----------------
    operator_out = staging / "operator"
    feed.write_fort_feed(
        operator_items, operator_out, fort_id=fort_id, fort_name=cfg.fort_name,
        fort_status=cfg.fort_status, projects=operator_projects, status=status_operator,
    )
    site_data.write_site_data(
        operator_out, agents_json=agents_json, tools_json=tools_json,
        gotchas_entries=gotchas_entries, public=False,
    )
    _write_runs(operator_out, fort_id, runs_operator)
    operator_hash = compute_content_hash(
        operator_items, operator_projects, hash_status_operator,
        site=_with_runs(_site_hash_payload(agents_json, tools_json, operator_gotchas), runs_operator),
    )
    if kill_switch_active:
        result["operator"]["reason"] = "kill_switch_file"
    elif cfg.operator_relay is None:
        result["operator"]["reason"] = "no_relay_configured"
    else:
        due = now - cursor.get("operator_last_push", 0) >= cfg.heartbeat_interval_seconds
        if operator_hash != cursor.get("operator_hash") or due:
            pusher(operator_out, cfg.operator_relay, delete=False, rsync_bin=cfg.rsync_bin)
            cursor["operator_hash"] = operator_hash
            cursor["operator_last_push"] = now
            result["operator"]["pushed"] = True
        else:
            result["operator"]["reason"] = "unchanged"

    # ---- public side: the kill-switch file OR public_enabled=false both
    # stop it, but only public_enabled=false actively clears it. -----------
    public_off = kill_switch_active or not cfg.public_enabled
    public_out = staging / "public"
    if public_off:
        feed.write_fort_feed(
            [], public_out, fort_id=fort_id, fort_name=cfg.fort_name,
            fort_status=cfg.fort_status,
            projects={"thread_to_project": {}, "projects": {}},
            status=None, state="off",
        )
    else:
        feed.write_fort_feed(
            public_items, public_out, fort_id=fort_id, fort_name=cfg.fort_name,
            fort_status=cfg.fort_status, projects=public_projects, status=status_public,
        )
    # Local staging is always written (same "keeps being written either
    # way" convention `write_fort_feed` above already follows) -- but when
    # the public side is off, it is excluded from the hash below, same as
    # `items`/`projects`/`status` are, so it never spuriously causes a push
    # while off and never counts toward "unchanged" once back on.
    site_data.write_site_data(
        public_out, agents_json=agents_json, tools_json=tools_json,
        gotchas_entries=gotchas_entries, public=True,
    )
    if not public_off:
        _write_runs(public_out, fort_id, runs_public)
    public_hash = compute_content_hash(
        [] if public_off else public_items,
        {"thread_to_project": {}, "projects": {}} if public_off else public_projects,
        None if public_off else hash_status_public,
        site=None if public_off else _with_runs(
            _site_hash_payload(agents_json, tools_json, public_gotchas), runs_public),
    )

    if kill_switch_active:
        result["public"]["reason"] = "kill_switch_file"
    elif cfg.public_relay is None:
        result["public"]["reason"] = "no_relay_configured"
    else:
        was_off = cursor.get("public_state") == "off"
        due = now - cursor.get("public_last_push", 0) >= cfg.heartbeat_interval_seconds
        changed = public_hash != cursor.get("public_hash")
        turned_off_now = public_off and not was_off
        if changed or due or turned_off_now:
            pusher(
                public_out, cfg.public_relay, delete=public_off, rsync_bin=cfg.rsync_bin,
            )
            cursor["public_hash"] = public_hash
            cursor["public_last_push"] = now
            cursor["public_state"] = "off" if public_off else "on"
            result["public"]["pushed"] = True
        else:
            result["public"]["reason"] = "already_off" if public_off else "unchanged"

    _write_cursor(cursor_path, cursor)
    return result


# ---- CLI --------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="the live queue SQLite file (read-only). STREAM_PUBLISHER_DB")
    parser.add_argument("--staging-dir", help="local directory to stage data/public and data/operator into. STREAM_PUBLISHER_STAGING_DIR")
    parser.add_argument("--kill-switch-file", help="if this file exists, nothing is pushed this cycle. STREAM_PUBLISHER_KILL_SWITCH_FILE")
    parser.add_argument("--public-disabled", action="store_true", default=None, help="design §4.6 layer 2: stop and clear the public side only, keep the operator side running")
    parser.add_argument("--heartbeat-interval", type=int, help="seconds between forced pushes even with no change. STREAM_PUBLISHER_HEARTBEAT_SECONDS")
    parser.add_argument("--loop-interval", type=int, help="seconds between cycles when not --once. STREAM_PUBLISHER_LOOP_SECONDS")
    parser.add_argument("--public-relay-host")
    parser.add_argument("--public-relay-user")
    parser.add_argument("--public-relay-path")
    parser.add_argument("--public-relay-ssh-key")
    parser.add_argument("--operator-relay-host")
    parser.add_argument("--operator-relay-user")
    parser.add_argument("--operator-relay-path")
    parser.add_argument("--operator-relay-ssh-key")
    parser.add_argument(
        "--fort-id", default=None,
        help="this fort's id for the multi-fort data/.../forts/<fort-id>/ layout "
             "(default: the --db file's own stem). STREAM_PUBLISHER_FORT_ID",
    )
    parser.add_argument(
        "--fort-name", default=None,
        help=f"this fort's display name (default: {DEFAULT_FORT_NAME}). STREAM_PUBLISHER_FORT_NAME",
    )
    parser.add_argument(
        "--fort-status", default=None, choices=list(_VALID_FORT_STATUSES),
        help="this fort's status for forts.json (default: live). STREAM_PUBLISHER_FORT_STATUS",
    )
    parser.add_argument(
        "--gotchas-db", default=None,
        help="a live gotcha-store SQLite file (read-only); omit for an honest empty "
             "gotchas.json. STREAM_PUBLISHER_GOTCHAS_DB",
    )
    parser.add_argument(
        "--live-journal", action="store_true", default=None,
        help="build the who-is-awake view from dfmcp-server's journal on this host "
             "(needs journal read access). STREAM_PUBLISHER_LIVE_JOURNAL",
    )
    parser.add_argument(
        "--conductor-dir", default=None,
        help="a local copy of the conductor's runtime root (status.json, cycles/): adds wake "
             "reason, run duration and (operator only) cost to the live view. STREAM_PUBLISHER_CONDUCTOR_DIR",
    )
    parser.add_argument(
        "--runs-db", default=None,
        help="the conductor's run-report store (dfqueue/runs.py), read-only. Default: the "
             "<queue db stem>.runs.sqlite3 file beside --db, if it exists. STREAM_PUBLISHER_RUNS_DB",
    )
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit (the systemd-timer-triggered mode, infra/stream-publisher.timer.example)")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="path to a .env file to merge under the real environment (default: repo root .env)")
    return parser


def _config_from_args(args: argparse.Namespace) -> PublisherConfig:
    """CLI flags override `.env`/the real environment, which `load_config`
    already merged -- the same precedence `dfmcp/server.py`'s own CLI
    wrapper (if any) would use: explicit beats implicit."""
    cfg = load_config(Path(args.env_file), validate=False)
    overrides: dict[str, Any] = {}
    if args.db:
        overrides["db_path"] = args.db
    if args.staging_dir:
        overrides["staging_dir"] = args.staging_dir
    if args.kill_switch_file:
        overrides["kill_switch_file"] = args.kill_switch_file
    if args.public_disabled:
        overrides["public_enabled"] = False
    if args.heartbeat_interval:
        overrides["heartbeat_interval_seconds"] = args.heartbeat_interval
    if args.loop_interval:
        overrides["loop_interval_seconds"] = args.loop_interval
    if args.fort_id:
        overrides["fort_id"] = args.fort_id
    if args.fort_name:
        overrides["fort_name"] = args.fort_name
    if args.fort_status:
        overrides["fort_status"] = args.fort_status
    if args.gotchas_db:
        overrides["gotchas_db"] = args.gotchas_db
    if args.live_journal:
        overrides["live_journal"] = True
    if args.conductor_dir:
        overrides["conductor_dir"] = args.conductor_dir
    if args.runs_db:
        overrides["runs_db"] = args.runs_db

    def _relay_override(prefix: str) -> Optional[RelayTarget]:
        host = getattr(args, f"{prefix}_relay_host")
        user = getattr(args, f"{prefix}_relay_user")
        path = getattr(args, f"{prefix}_relay_path")
        ssh_key = getattr(args, f"{prefix}_relay_ssh_key")
        if not any((host, user, path, ssh_key)):
            return None
        if not all((host, user, path, ssh_key)):
            raise ConfigError(f"--{prefix}-relay-* flags must all be given together")
        return RelayTarget(host=host, user=user, path=path, ssh_key=ssh_key)

    public_override = _relay_override("public")
    operator_override = _relay_override("operator")
    if public_override is not None:
        overrides["public_relay"] = public_override
    if operator_override is not None:
        overrides["operator_relay"] = operator_override

    for field_name, value in overrides.items():
        setattr(cfg, field_name, value)
    cfg.validate()
    return cfg


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        cfg = _config_from_args(args)
    except ConfigError as exc:
        print(f"stream_publisher: {exc}", file=sys.stderr)
        return 2

    if args.once:
        result = run_cycle(cfg)
        print(json.dumps(result, sort_keys=True))
        return 0

    print(
        f"stream_publisher: looping every {cfg.loop_interval_seconds}s "
        "(Ctrl-C to stop)",
        file=sys.stderr,
    )
    while True:
        try:
            result = run_cycle(cfg)
            print(json.dumps(result, sort_keys=True))
        except Exception as exc:  # noqa: BLE001 -- a cycle failure must never kill the loop
            print(f"stream_publisher: cycle failed: {exc}", file=sys.stderr)
        time.sleep(cfg.loop_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
