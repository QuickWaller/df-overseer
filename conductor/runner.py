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
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

LOG = logging.getLogger("conductor.runner")

#: The image repository every real run has used (research/2026-09-18-openclaw-
#: capabilities.md). Runs are pinned by DIGEST, never a floating tag: the
#: digest comes from `CONDUCTOR_OPENCLAW_IMAGE` (`infra/conductor.example.env`,
#: `ghcr.io/openclaw/openclaw@sha256:<64 hex>`; the Gateway S0 pinned
#: `sha256:cc596b84...f101`, truncated in its write-up, so the full value
#: lives in the VM's env file, not in this public repo's source).
IMAGE_REPOSITORY = "ghcr.io/openclaw/openclaw"
IMAGE_ENV_VAR = "CONDUCTOR_OPENCLAW_IMAGE"
#: Only used when the env var is unset (tests, a bare workstation). Wiring
#: code that must not run unpinned checks `image_is_pinned`.
FALLBACK_IMAGE = IMAGE_REPOSITORY + ":latest"


def image_is_pinned(image: str) -> bool:
    """True for `<repo>@sha256:<64 hex>`: a digest pin, not a tag."""
    return bool(re.fullmatch(r"[\w./:-]+@sha256:[0-9a-f]{64}", image or ""))


def resolve_image(environ: Optional[Dict[str, str]] = None) -> str:
    """The image to run: `CONDUCTOR_OPENCLAW_IMAGE` if set and a digest pin,
    else the unpinned fallback (callers that need a pin check `image_is_pinned`)."""
    value = ((environ if environ is not None else os.environ).get(IMAGE_ENV_VAR) or "").strip()
    return value if image_is_pinned(value) else FALLBACK_IMAGE


DEFAULT_IMAGE = resolve_image()

#: Failed or unparseable runs keep their raw stdout and stderr (Gateway S0
#: open item: the Quartermaster's empty envelope left nothing to diagnose).
RAW_RETENTION_CHARS = 65536


def retain_raw(
    stdout: Any, stderr: Any, exit_code: Optional[int], *, envelope: Optional[dict] = None,
) -> Dict[str, Any]:
    """The `RunResult.raw` of a failed run: the run's own stdout and stderr
    (each capped at `RAW_RETENTION_CHARS`, start and end kept) and its exit
    code. With a parsed `envelope`, the envelope's keys stay as they were and
    the retained text goes under `_stdout`, `_stderr`, `_exit_code`; without
    one the keys are `stdout`, `stderr`, `exit_code`."""
    def text(v: Any) -> str:
        t = v.decode("utf-8", errors="replace") if isinstance(v, (bytes, bytearray)) else (v or "")
        if len(t) <= RAW_RETENTION_CHARS:
            return t
        half = RAW_RETENTION_CHARS // 2
        return t[:half] + "\n[... middle left out ...]\n" + t[-half:]
    if envelope is None:
        return {"stdout": text(stdout), "stderr": text(stderr), "exit_code": exit_code}
    out = dict(envelope)
    out.update({"_stdout": text(stdout), "_stderr": text(stderr), "_exit_code": exit_code})
    return out

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

#: Where openclaw looks for the charter inside the container.
CHARTER_MOUNT = "/app/SOUL.md"

#: Bound on the best-effort `docker kill` after a timeout.
DOCKER_KILL_WAIT_SECONDS = 30.0


#: Cap on the reasoning text sent on (start and end kept, marker between).
THINKING_MAX_CHARS = 12000
THINKING_CUT_MARKER = "\n\n[... middle of the reasoning left out ...]\n\n"
#: Where the retained openclaw state dir is mounted inside the container.
THINKING_MOUNT = "/thinking"


def cap_thinking(text: Optional[str], limit: int = THINKING_MAX_CHARS) -> Optional[str]:
    """Keep the start and the end of `text` within `limit` characters."""
    if not text:
        return None
    if len(text) <= limit:
        return text
    room = max(0, limit - len(THINKING_CUT_MARKER))
    head = room // 2
    return text[:head].rstrip() + THINKING_CUT_MARKER + text[len(text) - (room - head):].lstrip()


def read_thinking(state_dir: Path) -> Optional[str]:
    """The reasoning text of the one run kept in `state_dir` (`agent exec
    --state-dir`), read from each agent db's `transcript_events` rows: the
    `thinking` blocks of assistant messages, in order, one paragraph per
    block. Never raises: None when nothing is there or the db cannot be read.
    See handoffs/2026-10-05-agent-thinking.md (findings)."""
    import sqlite3
    parts: List[str] = []
    try:
        for db in sorted(Path(state_dir).glob("agents/*/agent/openclaw-agent.sqlite")):
            conn = sqlite3.connect(db, timeout=5)
            try:
                rows = conn.execute(
                    "SELECT event_json FROM transcript_events ORDER BY session_id, seq"
                ).fetchall()
            finally:
                conn.close()
            for (raw,) in rows:
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                message = event.get("message") if isinstance(event, dict) else None
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        text = block.get("thinking")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
    except Exception as exc:  # noqa: BLE001 -- observability, never fails a run
        LOG.warning("conductor runner: could not read the run's reasoning: %s", exc)
        return None
    return cap_thinking("\n\n".join(parts)) if parts else None


# ---- the full transcript (handoffs/2026-10-07-transcripts-and-full-proposals.md)

#: Policy data: `transcript:` in `conductor/policy.yaml`. These are the
#: fallbacks when the block is absent or unreadable.
DEFAULT_TRANSCRIPT_CAPS: Dict[str, int] = {
    "max_rounds": 60,
    "max_call_args_chars": 600,
    "max_result_chars": 800,
    "max_round_text_chars": 2000,
    "max_total_chars": 60000,
}
_DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.yaml")


def load_transcript_caps(path: "Path | str | None" = None) -> Dict[str, int]:
    """The caps from policy.yaml's top-level `transcript:` block, each a
    positive int, falling back per key to `DEFAULT_TRANSCRIPT_CAPS`. Never
    raises (a bad file means defaults)."""
    caps = dict(DEFAULT_TRANSCRIPT_CAPS)
    try:
        import yaml
        doc = yaml.safe_load(Path(path or _DEFAULT_POLICY_PATH).read_text(encoding="utf-8")) or {}
        block = doc.get("transcript") if isinstance(doc, dict) else None
        if isinstance(block, dict):
            for key in caps:
                v = block.get(key)
                if isinstance(v, int) and not isinstance(v, bool) and v > 0:
                    caps[key] = v
    except Exception as exc:  # noqa: BLE001 -- observability, never fails a run
        LOG.warning("conductor runner: transcript caps unreadable, defaults used: %s", exc)
    return caps


def _clip(text: Any, limit: int) -> str:
    s = text if isinstance(text, str) else json.dumps(text, sort_keys=True, default=str)
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "\u2026"


def _block_text(content: Any) -> str:
    """The text of a message `content` (a string, or a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b["text"] for b in content
            if isinstance(b, dict) and isinstance(b.get("text"), str)
        )
    return ""


_CALL_TYPES = ("toolCall", "tool_use", "toolUse", "tool-call")


def _usage_of(message: dict) -> Optional[Dict[str, Any]]:
    raw = message.get("usage")
    if not isinstance(raw, dict):
        return None
    out: Dict[str, Any] = {}
    for key in USAGE_KEYS:
        n = _number(raw.get(key))
        if n is None and key == "total":
            n = _number(raw.get("totalTokens"))
        if n is not None:
            out[key] = n
    return out or None


def build_transcript(events: List[dict], caps: Optional[Dict[str, int]] = None) -> Optional[dict]:
    """Turn openclaw `transcript_events` payloads (in order) into the
    archived transcript: `{"rounds": [{"n", "reasoning", "text", "calls":
    [{"id", "name", "args", "result", "error"}], "usage"}], "omitted_rounds"}`.

    One round is one assistant message. Tool results (a `toolResult`-role
    message, matched by call id) attach to their call. UNVERIFIED against a
    live run: the thinking and text block shapes are proven
    (handoffs/2026-10-05-agent-thinking.md); the tool-call block and
    `toolResult` message shapes follow openclaw's pi-style message format
    and are read tolerantly (see `_CALL_TYPES`). Texts and results are
    capped per `caps`; when the whole thing would exceed `max_total_chars`
    the later rounds are dropped and counted, never silently."""
    caps = caps or DEFAULT_TRANSCRIPT_CAPS
    rounds: List[dict] = []
    by_call: Dict[str, dict] = {}
    for event in events:
        message = event.get("message") if isinstance(event, dict) else None
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role == "assistant":
            reasoning: List[str] = []
            texts: List[str] = []
            calls: List[dict] = []
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "thinking" and isinstance(block.get("thinking"), str):
                    reasoning.append(block["thinking"].strip())
                elif kind == "text" and isinstance(block.get("text"), str):
                    texts.append(block["text"].strip())
                elif kind in _CALL_TYPES:
                    args = block.get("arguments", block.get("input", block.get("args", {})))
                    call = {
                        "id": str(block.get("id") or ""),
                        "name": _clip(block.get("name") or "unknown", 80),
                        "args": _clip(args, caps["max_call_args_chars"]),
                        "result": None, "error": False,
                    }
                    calls.append(call)
                    if call["id"]:
                        by_call[call["id"]] = call
            if isinstance(content, str) and content.strip():
                texts.append(content.strip())
            rounds.append({
                "n": len(rounds) + 1,
                "reasoning": _clip("\n\n".join(r for r in reasoning if r), caps["max_round_text_chars"]) or None,
                "text": _clip("\n\n".join(t for t in texts if t), caps["max_round_text_chars"]) or None,
                "calls": calls, "usage": _usage_of(message),
            })
        elif role in ("toolResult", "tool"):
            call = by_call.get(str(message.get("toolCallId") or message.get("tool_call_id") or ""))
            if call is not None:
                call["result"] = _clip(_block_text(content), caps["max_result_chars"]) or None
                call["error"] = bool(message.get("isError"))
    if not rounds:
        return None
    omitted = max(0, len(rounds) - caps["max_rounds"])
    rounds = rounds[: caps["max_rounds"]]
    # The total cap: drop whole later rounds until the JSON fits.
    while len(rounds) > 1 and len(json.dumps(rounds, default=str)) > caps["max_total_chars"]:
        rounds.pop()
        omitted += 1
    return {"rounds": rounds, "omitted_rounds": omitted}


def read_transcript(state_dir: Path, caps: Optional[Dict[str, int]] = None) -> Optional[dict]:
    """The full turn sequence of the one run kept in `state_dir`, from the
    same `transcript_events` rows `read_thinking` reads. Never raises."""
    import sqlite3
    events: List[dict] = []
    try:
        for db in sorted(Path(state_dir).glob("agents/*/agent/openclaw-agent.sqlite")):
            conn = sqlite3.connect(db, timeout=5)
            try:
                rows = conn.execute(
                    "SELECT event_json FROM transcript_events ORDER BY session_id, seq"
                ).fetchall()
            finally:
                conn.close()
            for (raw,) in rows:
                try:
                    ev = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(ev, dict):
                    events.append(ev)
        return build_transcript(events, caps)
    except Exception as exc:  # noqa: BLE001 -- observability, never fails a run
        LOG.warning("conductor runner: could not read the run's transcript: %s", exc)
        return None


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


#: The `usage` keys kept in the archive, as openclaw names them (seen in the
#: real envelopes, `evals/live/2026-09-15-overseer-first-ruling/run.json`).
USAGE_KEYS = ("input", "output", "cacheRead", "cacheWrite", "reasoningTokens", "total")


def _number(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v


def usage_from(envelope: dict) -> Optional[Dict[str, Any]]:
    """The envelope's token `usage`, bounded: only the known keys, numbers
    only. A key the envelope lacks is absent here, never 0. None when the
    envelope carries no usable `usage`."""
    raw = envelope.get("usage")
    if not isinstance(raw, dict):
        return None
    out: Dict[str, Any] = {}
    for key in USAGE_KEYS:
        n = _number(raw.get(key))
        if n is not None:
            out[key] = n
    return out or None


def turns_from(envelope: dict) -> Optional[int]:
    """`assistantTurns` (model rounds in the run) if a non-negative number."""
    n = _number(envelope.get("assistantTurns"))
    return int(n) if n is not None and n >= 0 else None


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
    #: The run's reasoning text (capped), or None when not captured.
    thinking: Optional[str] = None
    #: Token usage from the envelope (`usage_from`): input, output, cacheRead,
    #: cacheWrite, reasoningTokens, total. None when unknown (killed run).
    usage: Optional[Dict[str, Any]] = None
    #: Model rounds in the run (`assistantTurns`); None when unknown.
    assistant_turns: Optional[int] = None
    #: The full turn sequence (`build_transcript`), or None when not captured.
    transcript: Optional[Dict[str, Any]] = None
    #: Gateway turns only (`conductor/session_runner.py`): the session key the
    #: turn ran in and the Gateway's run id. None for a one-shot run.
    session_key: Optional[str] = None
    run_id: Optional[str] = None


def map_exec_envelope(
    role: str, envelope: dict, wall_clock_seconds: float, *,
    stdout: Any = b"", stderr: Any = b"", exit_code: Optional[int] = None,
) -> RunResult:
    """`agent exec --json` envelope -> `RunResult`. A run that is not ok keeps
    its raw stdout, stderr and exit code next to the envelope (`retain_raw`);
    an ok run's `raw` is the envelope untouched."""
    ok = bool(envelope.get("ok", False))
    return RunResult(
        role=role,
        ok=ok,
        status=str(envelope.get("status", "unknown")),
        cost_usd=_cost_from(envelope),
        wall_clock_seconds=wall_clock_seconds,
        timed_out=False,
        tool_summary=envelope.get("toolSummary", {}) or {},
        final_answer=_final_answer(envelope),
        raw=envelope if ok else retain_raw(stdout, stderr, exit_code, envelope=envelope),
        usage=usage_from(envelope),
        assistant_turns=turns_from(envelope),
    )


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
        thinking_state_root: Optional[Path] = None,
        subprocess_exec: SubprocessExec = asyncio.create_subprocess_exec,
        clock: Callable[[], float] = time.monotonic,
        outer_kill_grace_seconds: float = OUTER_KILL_GRACE_SECONDS,
        transcript_caps: Optional[Dict[str, int]] = None,
    ):
        self.transcript_caps = transcript_caps or load_transcript_caps()
        self.pinned_config_dir = Path(pinned_config_dir)
        self.openclaw_state_dir = Path(openclaw_state_dir)
        self.workspace_root = Path(workspace_root)
        self.secrets_env_file = Path(secrets_env_file)
        self.image = image
        #: When set, each run keeps its openclaw session state under
        #: `<root>/<container name>` (`--state-dir`), the reasoning is read
        #: from it, and the dir is deleted. None: reasoning is not captured.
        self.thinking_state_root = None if thinking_state_root is None else Path(thinking_state_root)
        self._subprocess_exec = subprocess_exec
        self._clock = clock
        self._grace = outer_kill_grace_seconds

    @property
    def isolated_state(self) -> bool:
        """Every run gets its own openclaw `--state-dir` (so concurrent runs
        share no session state or lock): true when `thinking_state_root` is
        set. Workspaces are already per role."""
        return self.thinking_state_root is not None

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
        state_dir: Optional[Path] = None,
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
        # A fixed hostname per role: openclaw's system prompt ends in a
        # `## Runtime` line carrying `host=`, which was a fresh container id
        # each run and so changed the prompt prefix every time
        # (docs/CONDUCTOR-EXECUTION.md 3.1).
        hostname_args = ["--hostname", role]
        timeout_args = ["--timeout", str(int(timeout_seconds))] if timeout_seconds else []
        state_mount = ["-v", f"{state_dir}:{THINKING_MOUNT}"] if state_dir else []
        state_args = ["--state-dir", THINKING_MOUNT] if state_dir else []
        return [
            "docker", "run", "--rm", *name_args, *hostname_args, "--entrypoint", "node",
            "--env-file", str(self.secrets_env_file),
            "-v", f"{self.openclaw_state_dir}:/home/node/.openclaw",
            "-v", f"{self.pinned_config_dir / (role + '.json')}:/home/node/.openclaw/openclaw.json:ro",
            "-v", f"{self._workspace_dir(role)}:{self._workspace_dir(role)}",
            # openclaw injects its bootstrap files from the container cwd
            # (/app), not the configured workspace: without this mount the
            # charter reads `[MISSING]` in the model's system prompt
            # (evals/live/2026-10-08-charter-delivery). /app ships no SOUL.md.
            "-v", f"{self._workspace_dir(role) / 'SOUL.md'}:{CHARTER_MOUNT}:ro",
            *state_mount,
            self.image, "openclaw.mjs", "agent", "exec", "--json",
            *state_args, *timeout_args, "--model", model, prompt,
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
        if charter is None or not charter.strip():
            # A role without its charter must never run: it would silently
            # work from tool descriptions alone (2026-10-08 finding).
            return self._failed_run(
                role, "charter_missing", started, "refusing to run without a charter",
                ValueError(f"charter for role {role} is absent or empty"),
            )
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
                    raw=result.raw, usage=result.usage, assistant_turns=result.assistant_turns,
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
        state_dir: Optional[Path] = None
        if self.thinking_state_root is not None:
            try:
                state_dir = self.thinking_state_root / container_name
                state_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:  # noqa: BLE001 -- the run goes on without it
                LOG.warning("conductor runner: no reasoning state dir, run goes on: %s", exc)
                state_dir = None
        try:
            result = await self._launch(
                role, prompt, model=model, timeout_seconds=timeout_seconds, started=started,
                container_name=container_name, state_dir=state_dir,
            )
            if state_dir is not None and result.status == "ok":
                result = replace(
                    result, thinking=read_thinking(state_dir),
                    transcript=read_transcript(state_dir, self.transcript_caps),
                )
            return result
        finally:
            if state_dir is not None:
                shutil.rmtree(state_dir, ignore_errors=True)

    async def _launch(
        self, role: str, prompt: str, *, model: str, timeout_seconds: float, started: float,
        container_name: str, state_dir: Optional[Path],
    ) -> RunResult:
        command = self.build_command(
            role, prompt, model=model, container_name=container_name,
            timeout_seconds=timeout_seconds, state_dir=state_dir,
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
                tool_summary={}, final_answer=None,
                raw=retain_raw(b"", b"", None),
                error=f"timed out after {timeout_seconds + self._grace}s (cost unknown)",
            )

        wall_clock = self._clock() - started
        text = stdout.decode("utf-8", errors="replace").strip()
        if not text:
            return RunResult(
                role=role, ok=False, status="no_output", cost_usd=None,
                wall_clock_seconds=wall_clock, timed_out=False, tool_summary={}, final_answer=None,
                raw=retain_raw(stdout, stderr, process.returncode),
                error="agent exec --json printed nothing",
            )
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError:
            return RunResult(
                role=role, ok=False, status="bad_json", cost_usd=None,
                wall_clock_seconds=wall_clock, timed_out=False, tool_summary={}, final_answer=None,
                raw=retain_raw(stdout, stderr, process.returncode),
                error="agent exec --json did not print valid JSON",
            )

        return map_exec_envelope(
            role, envelope, wall_clock, stdout=stdout, stderr=stderr,
            exit_code=process.returncode,
        )
