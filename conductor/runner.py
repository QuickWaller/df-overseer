"""Launching a role: `docs/AGENT-LOOP.md` item 1's "Launching a role" bullet
and build item 3's own row -- "launches `docker run --rm ... agent exec` as
the 2026-09-16 run did; archives each run's JSON, tool calls and `costUsd`."

One `docker run --rm ... agent exec --json` per role per cycle, fresh
context, the charter from `agents/<role>/role.md` written as the workspace's
`SOUL.md` before the run and removed after -- the exact mechanism
`evals/live/2026-09-15-overseer-first-ruling/README.md` and its sibling runs
record, including the traps they hit:

- `agents.defaults.systemAgent.agentId` must name the role in the pinned
  config mounted for that run -- the parent `agent` command's own `--agent`
  flag does NOT select the agent for `agent exec` in a multi-agent config
  (found the hard way, same README, "Two real, previously-undocumented
  schema/runtime requirements"). This module therefore expects one pinned
  config file per role (`pinned_config_dir/<role>.json`), each already
  carrying its own `systemAgent.agentId`, rather than trying to select a
  role via a CLI flag.
- Secrets only via `--env-file`, never argv or a tracked file (the same run's
  own hard line, honoured here: `secrets_env_file` is a path, its contents
  are never read by this module).
- `ghcr.io/openclaw/openclaw:latest`, `--entrypoint node`, `openclaw.mjs`,
  matching every real run 2026-09-14 through 2026-09-18
  (`research/2026-09-18-openclaw-capabilities.md`).

Nothing here ever runs for real in this stream -- **hard line: no Docker run
of openclaw.** `DockerOpenClawRunner` is written for the deploy to use, and
is exercised in tests only through an injected fake `subprocess_exec`
function (default `asyncio.create_subprocess_exec`) that a test replaces
with something that never touches a real container -- see
`conductor/tests/test_runner.py`. `FakeRoleRunner` is the double
`conductor/cycle.py`'s own tests use instead of this class entirely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

LOG = logging.getLogger("conductor.runner")

#: The image every real run so far has used, unchanged 2026-09-14 through
#: 2026-09-18 (research/2026-09-18-openclaw-capabilities.md).
DEFAULT_IMAGE = "ghcr.io/openclaw/openclaw:latest"

#: openclaw's own `agent exec --help` documents 600s as its default
#: deadline; kept the same here rather than invented, and overridable per
#: role by the caller.
DEFAULT_TIMEOUT_SECONDS = 600.0

#: The inner deadline handed to `agent exec --timeout` is the role cap; the
#: outer (conductor-side) kill fires this many seconds later. The point is
#: that openclaw gets to hit its own deadline first and, if it prints its
#: envelope then, `costUsd` and `toolSummary` survive. Not verified live
#: that the envelope is printed on an inner deadline; if it is not, the
#: outer kill still applies and cost stays unknown (None).
OUTER_KILL_GRACE_SECONDS = 60.0

#: Bound on the best-effort `docker kill` after a timeout.
DOCKER_KILL_WAIT_SECONDS = 30.0


def _final_answer(envelope: dict) -> Optional[str]:
    """The agent's answer text. Order: `finalAnswer`, `final_answer`, `final`
    (the shape the real openclaw envelope returns, seen 2026-09-24), then the
    first non-empty `payloads[].text`. First non-empty string wins."""
    for key in ("finalAnswer", "final_answer", "final"):
        v = envelope.get(key)
        if isinstance(v, str) and v:
            return v
    payloads = envelope.get("payloads")
    if isinstance(payloads, list):
        for p in payloads:
            if isinstance(p, dict) and isinstance(p.get("text"), str) and p["text"]:
                return p["text"]
    return None


def _cost_from(envelope: dict) -> Optional[float]:
    """`costUsd` if the envelope carries a number, else None (unknown).
    A present 0 is a real zero; an absent or malformed field is not."""
    v = envelope.get("costUsd")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


@dataclass(frozen=True)
class RunResult:
    """The one shape every `RoleRunner` returns, real or fake. Mirrors
    openclaw's own "stable agent-exec JSON envelope"
    (`research/2026-09-18-openclaw-capabilities.md`: `toolSummary`, `usage`,
    `costUsd`, `assistantTurns`) closely enough that `conductor/archive.py`
    can write it straight to `run-<role>.json`, plus the fields the
    conductor itself needs that the envelope does not carry."""

    role: str
    ok: bool
    status: str
    #: None means UNKNOWN (killed run, missing `costUsd`), never 0.0.
    cost_usd: Optional[float]
    wall_clock_seconds: float
    timed_out: bool
    tool_summary: Dict[str, Any]
    final_answer: Optional[str]
    raw: Dict[str, Any]
    error: Optional[str] = None


class RoleRunner(Protocol):
    async def run(
        self, role: str, prompt: str, *, model: str, timeout_seconds: float,
        charter: Optional[str] = None,
    ) -> RunResult: ...


class FakeRoleRunner:
    """Test double: returns a caller-supplied `RunResult` per role (or a
    default "passed, nothing proposed" result), and records every call made
    -- what `conductor/tests/test_cycle.py` asserts against to prove the
    cycle launched exactly the roles triage said to, with the right
    prompt/model/charter. Never touches a subprocess, a container, or the
    network."""

    def __init__(self, results: Optional[Dict[str, RunResult]] = None):
        self._results: Dict[str, RunResult] = dict(results or {})
        self.calls: List[Dict[str, Any]] = []

    def set_result(self, role: str, result: RunResult) -> None:
        self._results[role] = result

    async def run(
        self, role: str, prompt: str, *, model: str, timeout_seconds: float,
        charter: Optional[str] = None,
    ) -> RunResult:
        self.calls.append({
            "role": role, "prompt": prompt, "model": model, "timeout_seconds": timeout_seconds,
            "charter": charter,
        })
        if role in self._results:
            return self._results[role]
        return RunResult(
            role=role, ok=True, status="ok", cost_usd=0.0, wall_clock_seconds=0.0,
            timed_out=False, tool_summary={"calls": 0, "distinctTools": 0, "failures": 0},
            final_answer="(fake runner: no proposal, passed)", raw={},
        )


SubprocessExec = Callable[..., Awaitable[Any]]


class DockerOpenClawRunner:
    """The real launcher. See this module's docstring for the exact
    mechanism and why nothing here is ever exercised against real docker in
    this stream."""

    def __init__(
        self, *, pinned_config_dir: Path, openclaw_state_dir: Path, workspace_root: Path,
        secrets_env_file: Path, image: str = DEFAULT_IMAGE,
        subprocess_exec: SubprocessExec = asyncio.create_subprocess_exec,
        clock: Callable[[], float] = time.monotonic,
        outer_kill_grace_seconds: float = OUTER_KILL_GRACE_SECONDS,
    ):
        self.pinned_config_dir = Path(pinned_config_dir)
        self.openclaw_state_dir = Path(openclaw_state_dir)
        self.workspace_root = Path(workspace_root)
        self.secrets_env_file = Path(secrets_env_file)
        self.image = image
        self._subprocess_exec = subprocess_exec
        self._clock = clock
        self._grace = outer_kill_grace_seconds

    def _workspace_dir(self, role: str) -> Path:
        return self.workspace_root / f"{role}-workspace"

    def write_soul(self, role: str, charter_markdown: str) -> Path:
        """Place `agents/<role>/role.md` (the caller reads it; this module
        never reads agents/ itself) as this role's workspace `SOUL.md`,
        matching `agents.entries.<role>.workspace` in that role's pinned
        config. Created fresh each call, per the 2026-09-15 run's own
        convention ("workspace... created fresh... before use")."""
        workspace = self._workspace_dir(role)
        workspace.mkdir(parents=True, exist_ok=True)
        soul_path = workspace / "SOUL.md"
        soul_path.write_text(charter_markdown, encoding="utf-8")
        return soul_path

    def cleanup_workspace(self, role: str) -> None:
        """Delete this role's `SOUL.md` after the run, per every real run's
        own cleanup convention (`evals/live/*/README.md`, "Cleanup and
        reversal"). Never raises if already gone."""
        (self._workspace_dir(role) / "SOUL.md").unlink(missing_ok=True)

    def build_command(
        self, role: str, prompt: str, *, model: str,
        container_name: Optional[str] = None, timeout_seconds: Optional[float] = None,
    ) -> List[str]:
        """The exact docker invocation: `--rm`, `--entrypoint node`, the
        persisted openclaw state dir bind-mounted read-write at
        `/home/node/.openclaw` (shares the auth profile and plugin registry
        every real run has relied on), this role's own pinned config
        overlaid **read-only** onto `openclaw.json`, the secrets env-file,
        then `openclaw.mjs agent exec --json --model <model> <prompt>`.
        `prompt` is passed as the final positional argument -- `agent exec`
        takes it verbatim on the command line in every real run this
        project has done, never over stdin.
        """
        name_args = ["--name", container_name] if container_name else []
        timeout_args = ["--timeout", str(int(timeout_seconds))] if timeout_seconds else []
        return [
            "docker", "run", "--rm", *name_args, "--entrypoint", "node",
            "--env-file", str(self.secrets_env_file),
            "-v", f"{self.openclaw_state_dir}:/home/node/.openclaw",
            "-v", f"{self.pinned_config_dir / (role + '.json')}:/home/node/.openclaw/openclaw.json:ro",
            "-v", f"{self._workspace_dir(role)}:{self._workspace_dir(role)}",
            self.image, "openclaw.mjs", "agent", "exec", "--json",
            *timeout_args, "--model", model, prompt,
        ]

    async def _kill_container(self, container_name: str) -> None:
        """`docker kill <name>`, best effort: never raises, bounded wait."""
        try:
            proc = await self._subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=DOCKER_KILL_WAIT_SECONDS)
        except Exception:
            pass

    async def run(
        self, role: str, prompt: str, *, model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        charter: Optional[str] = None,
    ) -> RunResult:
        """`charter`, if given, is written as this role's workspace
        `SOUL.md` before launch and removed after -- success or failure --
        matching every real run's own convention (`write_soul`/
        `cleanup_workspace`'s own docstrings). `charter=None` (a role whose
        deploy config already carries a persisted charter another way) skips
        both steps."""
        started = self._clock()
        if charter is not None:
            try:
                self.write_soul(role, charter)
            except Exception as exc:  # e.g. root-owned workspace (PermissionError)
                return self._failed_run(role, "launch_failed", started, "write_soul failed", exc)
        result = await self._run_launched(
            role, prompt, model=model, timeout_seconds=timeout_seconds, started=started,
        )
        if charter is not None:
            try:
                self.cleanup_workspace(role)
            except Exception as exc:
                # The run happened and may have cost money: keep its cost and
                # timing, but record the run as failed so it is never trusted.
                failed = self._failed_run(role, "cleanup_failed", started, "cleanup_workspace failed", exc)
                return replace(
                    failed, cost_usd=result.cost_usd, timed_out=result.timed_out,
                    tool_summary=result.tool_summary, final_answer=result.final_answer,
                    raw=result.raw,
                )
        return result

    def _failed_run(
        self, role: str, status: str, started: float, what: str, exc: Exception,
    ) -> RunResult:
        LOG.error("conductor runner: %s for role %s: %s: %s", what, role, type(exc).__name__, exc)
        return RunResult(
            role=role, ok=False, status=status, cost_usd=None,
            wall_clock_seconds=self._clock() - started, timed_out=False,
            tool_summary={}, final_answer=None, raw={},
            error=f"{what}: {type(exc).__name__}: {exc}",
        )

    async def _run_launched(
        self, role: str, prompt: str, *, model: str, timeout_seconds: float, started: float,
    ) -> RunResult:
        container_name = f"conductor-{role}-{uuid.uuid4().hex[:12]}"
        command = self.build_command(
            role, prompt, model=model, container_name=container_name,
            timeout_seconds=timeout_seconds,
        )

        try:
            process = await self._subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:  # docker itself missing, permission denied, etc.
            return RunResult(
                role=role, ok=False, status="launch_failed", cost_usd=None,
                wall_clock_seconds=self._clock() - started, timed_out=False,
                tool_summary={}, final_answer=None, raw={}, error=f"{type(exc).__name__}: {exc}",
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds + self._grace,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            # Killing the `docker run` client does NOT stop the
            # container (it keeps running, and spending, detached from
            # the client). Stop it by name, best effort.
            await self._kill_container(container_name)
            return RunResult(
                role=role, ok=False, status="timeout", cost_usd=None,
                wall_clock_seconds=self._clock() - started, timed_out=True,
                tool_summary={}, final_answer=None, raw={},
                error=f"timed out after {timeout_seconds + self._grace}s (cost unknown)",
            )

        wall_clock = self._clock() - started
        text = stdout.decode("utf-8", errors="replace").strip()
        if not text:
            return RunResult(
                role=role, ok=False, status="no_output", cost_usd=None,
                wall_clock_seconds=wall_clock, timed_out=False, tool_summary={}, final_answer=None,
                raw={"stderr": stderr.decode("utf-8", errors="replace")},
                error="agent exec --json printed nothing",
            )
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError:
            return RunResult(
                role=role, ok=False, status="bad_json", cost_usd=None,
                wall_clock_seconds=wall_clock, timed_out=False, tool_summary={}, final_answer=None,
                raw={"stdout": text, "stderr": stderr.decode("utf-8", errors="replace")},
                error="agent exec --json did not print valid JSON",
            )

        return RunResult(
            role=role,
            ok=bool(envelope.get("ok", False)),
            status=str(envelope.get("status", "unknown")),
            cost_usd=_cost_from(envelope),
            wall_clock_seconds=wall_clock,
            timed_out=False,
            tool_summary=envelope.get("toolSummary", {}) or {},
            final_answer=_final_answer(envelope),
            raw=envelope,
        )
