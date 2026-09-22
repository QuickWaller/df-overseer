"""The conductor service's entry point: `docs/AGENT-LOOP.md` build item 1's
own row -- "Python. Runs the cycle, triage, the clock policy; launches
`docker run --rm ... agent exec` as the 2026-09-16 run did; archives each
run's JSON, tool calls and `costUsd` under `runtime/` for the public
report."

Wires the real `StreamableHTTPMCPClient`, `DockerOpenClawRunner`, loaded
`Policy`, `CursorStore`, `CycleArchive` and each role's charter (read fresh
every cycle from `agents/<role>/role.md`, the same file this repo's own
roster validation already treats as that role's source of truth) into
`conductor/cycle.py`'s `run_cycle`, in a loop at
`CONDUCTOR_CYCLE_INTERVAL_SECONDS`, writing a status JSON and a journald log
line every cycle.

**Never run in this stream** -- hard line: no VM, no model call, no Docker
run of openclaw, no push. `python -m conductor.service --dry-run --once`
would still try to reach a real `dfmcp` server over HTTP using config that
names real infra this stream has no access to, so it is described here, in
this docstring and this stream's report, rather than executed.
`conductor/tests/test_service.py` exercises `run_forever` itself against an
already-built, fully fake `CycleDeps` -- the one thing in this module with
real logic worth testing without a live connection.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from conductor.archive import CycleArchive
from conductor.config import ConductorConfig, load_config
from conductor.cursors import CursorStore
from conductor.cycle import CycleDeps, CycleError, run_cycle
from conductor.mcp_client import StreamableHTTPMCPClient
from conductor.policy import load_policy
from conductor.runner import DockerOpenClawRunner
from conductor.status import configure_logging, log_cycle, status_from_cycle, write_status
from conductor.triage import ADVISORS, CONSULTANT, OVERSEER

LOG = logging.getLogger("conductor.service")

#: The four roles this MVP roster launches (docs/AGENT-LOOP.md §4). The
#: conductor's own charter (agents/conductor/role.md) is never loaded here
#: -- it documents this service to a human reader, never a model, per that
#: file's own header.
ROLES = (*ADVISORS, CONSULTANT, OVERSEER)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AGENTS_DIR = REPO_ROOT / "agents"


def load_charters(agents_dir: Path = DEFAULT_AGENTS_DIR) -> Dict[str, str]:
    """Read fresh every call, never cached -- an edited `role.md` takes
    effect on the NEXT cycle with no service restart, the same "re-read on
    every call" convention `dfmcp.doctrine_tools` already applies to
    `doctrine/seed.yaml`."""
    charters: Dict[str, str] = {}
    for role in ROLES:
        role_md = agents_dir / role / "role.md"
        charters[role] = role_md.read_text(encoding="utf-8")
    return charters


def build_deps(config: ConductorConfig, *, dry_run: bool, agents_dir: Path = DEFAULT_AGENTS_DIR) -> CycleDeps:
    """The one place the real, uninjected `StreamableHTTPMCPClient`/
    `DockerOpenClawRunner` get constructed. Never called by any test in
    this package -- constructing these is safe (no I/O happens until a
    method is actually called), but this stream's hard line is "no VM, no
    Docker run", so the boundary is kept here, one function, never
    exercised."""
    tool_caller = StreamableHTTPMCPClient(config.mcp_url, config.mcp_conductor_token)
    role_runner = DockerOpenClawRunner(
        pinned_config_dir=config.pinned_config_dir,
        openclaw_state_dir=config.openclaw_state_dir,
        workspace_root=config.workspace_root,
        secrets_env_file=config.secrets_env_file,
    )
    policy = load_policy(config.policy_path)
    return CycleDeps(
        tool_caller=tool_caller,
        role_runner=role_runner,
        policy=policy,
        cursor_store=CursorStore(config.cursor_store_path),
        archive=CycleArchive(config.runtime_root),
        charters=load_charters(agents_dir),
        models=dict(config.models),
        role_timeout_seconds=config.role_timeout_seconds,
        dry_run=dry_run,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_forever(
    deps: CycleDeps, *, status_path: Path, cycle_interval_seconds: float,
    once: bool = False, sleep=asyncio.sleep,
) -> int:
    """The loop itself, over an already-built `CycleDeps` -- every real
    side effect (the MCP connection, the docker launches, the clock) lives
    inside `deps`, so this function's own logic (loop, status write,
    logging, `--once`) is exactly what `conductor/tests/test_service.py`
    exercises with a fully fake `deps`. Returns the number of cycles run.
    """
    write_status(status_path, {"state": "starting", "updated_at": _now_iso()})
    cycle_index = 0
    while True:
        cycle_index += 1
        try:
            result = await run_cycle(cycle_index, deps)
        except CycleError as exc:
            LOG.error("cycle %s could not complete: %s", cycle_index, exc)
            write_status(status_path, {
                "state": "read_failed", "updated_at": _now_iso(), "error": str(exc),
                "cycle_index": cycle_index,
            })
        else:
            log_cycle(result)
            write_status(status_path, status_from_cycle(result))
            if result.dry_run:
                LOG.info("cycle %s dry-run plan: %s", cycle_index, result.plan)

        if once:
            return cycle_index
        await sleep(cycle_interval_seconds)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m conductor.service",
        description=(
            "The conductor: reads the fort, grades, triages, wakes roles, sets the "
            "clock, archives every cycle. Never runs the write half of a cycle in "
            "--dry-run mode."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Read and print what this cycle would do -- who it would wake and at "
            "what clock level -- without calling any model, changing the clock, "
            "grading, quicksaving or launching anyone."
        ),
    )
    parser.add_argument("--once", action="store_true", help="Run exactly one cycle then exit, instead of looping.")
    parser.add_argument(
        "--env-file", type=Path, default=None,
        help="Path to a .env file to merge under the real environment (never read for a dry run's own config values that are absent -- ConfigError still applies).",
    )
    args = parser.parse_args(argv)

    configure_logging()
    config = load_config(args.env_file)
    deps = build_deps(config, dry_run=args.dry_run)
    asyncio.run(run_forever(
        deps, status_path=config.status_path,
        cycle_interval_seconds=config.cycle_interval_seconds, once=args.once,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover -- never run in this stream; see module docstring
    sys.exit(main())
